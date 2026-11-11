#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include "MAX30105.h"
#include "heartRate.h"
#include "telemetry.h"

#ifndef ASTRA_DEVICE_ID
#define ASTRA_DEVICE_ID "astra-01"
#endif

#ifndef ASTRA_PPG_CONTACT_IR
#define ASTRA_PPG_CONTACT_IR 50000
#endif

#ifndef ASTRA_MOTION_RANGE_M_S2
#define ASTRA_MOTION_RANGE_M_S2 3.0f
#endif

using astra::Contact;
using astra::Missing;
using astra::Value;

namespace {

constexpr uint32_t kBaudRate = 115200;
constexpr uint32_t kI2cHz = 400000;
constexpr uint32_t kReportPeriodMs = 1000;
constexpr uint32_t kAccelPeriodUs = 20000;
constexpr uint32_t kRetryPeriodMs = 5000;

enum class State : uint8_t { NotPresent, Ready, Error };

struct Sensor {
  State state = State::NotPresent;
};

Sensor ppgSensor;
Sensor tempSensor;
Sensor imuSensor;

MAX30105 ppg;
astra::AccelWindow accel;
astra::BeatAverager beats;

uint32_t seq = 0;
uint32_t nextReportMs = 0;
uint32_t nextAccelUs = 0;
uint32_t nextRetryMs = 0;
double irSum = 0.0;
uint32_t irCount = 0;

bool writeRegister(uint8_t address, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t address, uint8_t reg, uint8_t *out, size_t length) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(address, static_cast<uint8_t>(length)) != length) {
    return false;
  }
  for (size_t i = 0; i < length; i++) {
    out[i] = Wire.read();
  }
  return true;
}

bool present(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void initSensors() {
  if (ppgSensor.state != State::Ready) {
    const bool had = ppgSensor.state == State::Error;
    if (ppg.begin(Wire, I2C_SPEED_FAST)) {
      ppg.setup(0x1F, 4, 2, 400, 411, 4096);
      ppgSensor.state = State::Ready;
    } else {
      ppgSensor.state = had ? State::Error : State::NotPresent;
    }
  }
  if (tempSensor.state != State::Ready) {
    const bool had = tempSensor.state == State::Error;
    if (present(astra::max30205::kAddress) && writeRegister(astra::max30205::kAddress, astra::max30205::kConfigRegister, 0x00)) {
      tempSensor.state = State::Ready;
    } else {
      tempSensor.state = had ? State::Error : State::NotPresent;
    }
  }
  if (imuSensor.state != State::Ready) {
    const bool had = imuSensor.state == State::Error;
    if (present(astra::mpu6050::kAddress) && writeRegister(astra::mpu6050::kAddress, astra::mpu6050::kPowerRegister, 0x00) &&
        writeRegister(astra::mpu6050::kAddress, astra::mpu6050::kConfigRegister, 0x03) &&
        writeRegister(astra::mpu6050::kAddress, astra::mpu6050::kAccelConfigRegister, 0x18)) {
      imuSensor.state = State::Ready;
    } else {
      imuSensor.state = had ? State::Error : State::NotPresent;
    }
  }
}

void pollPpg() {
  if (ppgSensor.state != State::Ready) {
    return;
  }
  ppg.check();
  while (ppg.available()) {
    const uint32_t ir = ppg.getFIFOIR();
    ppg.nextSample();
    irSum += ir;
    irCount++;
    if (ir >= ASTRA_PPG_CONTACT_IR && checkForBeat(ir)) {
      beats.beat(millis());
    }
  }
}

void sampleAccel() {
  if (imuSensor.state != State::Ready) {
    return;
  }
  uint8_t raw[6];
  if (!readRegisters(astra::mpu6050::kAddress, astra::mpu6050::kAccelDataRegister, raw, sizeof raw)) {
    imuSensor.state = State::Error;
    return;
  }
  accel.add(astra::accelMagnitude(raw));
}

Value readTemperature() {
  if (tempSensor.state != State::Ready) {
    return Value::absent(tempSensor.state == State::Error ? Missing::SensorError
                                                          : Missing::NotPresent);
  }
  uint8_t raw[2];
  if (!readRegisters(astra::max30205::kAddress, astra::max30205::kTemperatureRegister, raw, sizeof raw)) {
    tempSensor.state = State::Error;
    return Value::absent(Missing::SensorError);
  }
  return Value::within(astra::temperatureCelsius(raw), 0.0f, 60.0f);
}

void report(uint32_t nowMs) {
  const bool motion = accel.motionArtifact(ASTRA_MOTION_RANGE_M_S2);
  beats.endSecond(motion, nowMs);

  Contact contact = Contact::Unknown;
  Value heartRate = Value::absent(ppgSensor.state == State::NotPresent ? Missing::NotPresent
                                                                       : Missing::SensorError);
  if (ppgSensor.state == State::Ready && irCount == 0) {
    ppgSensor.state = State::Error;
  }
  if (ppgSensor.state == State::Ready) {
    const double meanIr = irSum / irCount;
    float bpm;
    if (meanIr < ASTRA_PPG_CONTACT_IR) {
      contact = Contact::Lost;
      beats.clear();
      heartRate = Value::absent(Missing::NoContact);
    } else {
      contact = Contact::Ok;
      heartRate = beats.bpm(nowMs, bpm) ? Value::within(bpm, 0.0f, 300.0f)
                                        : Value::absent(Missing::WarmingUp);
    }
  }

  Value accelMin;
  Value accelMax;
  Value accelMean;
  if (accel.count() > 0) {
    accelMin = Value::within(accel.min(), 0.0f, 200.0f);
    accelMax = Value::within(accel.max(), 0.0f, 200.0f);
    accelMean = Value::within(accel.mean(), 0.0f, 200.0f);
  } else {
    const Value none = Value::absent(imuSensor.state == State::NotPresent ? Missing::NotPresent
                                                                          : Missing::SensorError);
    accelMin = accelMax = accelMean = none;
  }

  const astra::Sample sample = {ASTRA_DEVICE_ID, seq, nowMs, heartRate, readTemperature(),
                                accelMin,        accelMax, accelMean, contact, motion};
  char line[astra::kLineSize];
  const size_t length = astra::formatLine(line, sizeof line, sample);
  if (length > 0) {
    Serial.write(reinterpret_cast<const uint8_t *>(line), length);
    Serial.write('\n');
  }

  seq++;
  accel.reset();
  irSum = 0.0;
  irCount = 0;
}

}  // namespace

void setup() {
  Serial.begin(kBaudRate);
  Wire.begin();
  Wire.setClock(kI2cHz);
  initSensors();
  nextReportMs = millis() + kReportPeriodMs;
  nextAccelUs = micros() + kAccelPeriodUs;
  nextRetryMs = millis() + kRetryPeriodMs;
}

void loop() {
  pollPpg();

  const uint32_t nowUs = micros();
  if (static_cast<int32_t>(nowUs - nextAccelUs) >= 0) {
    nextAccelUs += kAccelPeriodUs;
    if (static_cast<int32_t>(nowUs - nextAccelUs) >= 5 * static_cast<int32_t>(kAccelPeriodUs)) {
      nextAccelUs = nowUs + kAccelPeriodUs;
    }
    sampleAccel();
  }

  const uint32_t nowMs = millis();
  if (static_cast<int32_t>(nowMs - nextReportMs) >= 0) {
    nextReportMs += kReportPeriodMs;
    report(nowMs);
  }
  if (static_cast<int32_t>(nowMs - nextRetryMs) >= 0) {
    nextRetryMs += kRetryPeriodMs;
    initSensors();
  }
}
