#pragma once

#include <stddef.h>
#include <stdint.h>

namespace astra {

enum class Missing : uint8_t { None, NoContact, WarmingUp, SensorError, NotPresent };

enum class Contact : uint8_t { Ok, Lost, Unknown };

struct Value {
  bool valid;
  float number;
  Missing reason;

  static Value absent(Missing reason);
  static Value within(float number, float low, float high);
};

struct Sample {
  const char *deviceId;
  uint32_t seq;
  uint32_t uptimeMs;
  Value heartRate;
  Value temperature;
  Value accelMin;
  Value accelMax;
  Value accelMean;
  Contact contact;
  bool motionArtifact;
};

constexpr size_t kLineSize = 640;

namespace max30205 {
constexpr uint8_t kAddress = 0x48;
constexpr uint8_t kTemperatureRegister = 0x00;
constexpr uint8_t kConfigRegister = 0x01;
constexpr float kCelsiusPerCount = 0.00390625f;
}  // namespace max30205

namespace mpu6050 {
constexpr uint8_t kAddress = 0x68;
constexpr uint8_t kConfigRegister = 0x1A;
constexpr uint8_t kAccelConfigRegister = 0x1C;
constexpr uint8_t kAccelDataRegister = 0x3B;
constexpr uint8_t kPowerRegister = 0x6B;
constexpr float kCountsPerG = 2048.0f;
constexpr float kGravity = 9.80665f;
}  // namespace mpu6050

float temperatureCelsius(const uint8_t raw[2]);
float accelMagnitude(const uint8_t raw[6]);

size_t formatLine(char *out, size_t size, const Sample &sample);

class AccelWindow {
 public:
  void reset();
  void add(float magnitude);
  size_t count() const { return count_; }
  float min() const { return min_; }
  float max() const { return max_; }
  float mean() const { return count_ == 0 ? 0.0f : sum_ / count_; }
  bool motionArtifact(float rangeThreshold) const;

 private:
  size_t count_ = 0;
  float min_ = 0.0f;
  float max_ = 0.0f;
  float sum_ = 0.0f;
};

class BeatAverager {
 public:
  static constexpr uint32_t kStaleMs = 10000;

  void clear();
  void beat(uint32_t nowMs);
  void endSecond(bool motionArtifact, uint32_t nowMs);
  bool bpm(uint32_t nowMs, float &out) const;

 private:
  static constexpr size_t kRates = 4;
  static constexpr size_t kPending = 8;

  bool hasLastBeat_ = false;
  uint32_t lastBeatMs_ = 0;
  uint32_t lastCommitMs_ = 0;
  uint8_t rates_[kRates] = {};
  size_t rateCount_ = 0;
  size_t rateNext_ = 0;
  uint8_t pending_[kPending] = {};
  size_t pendingCount_ = 0;
};

}  // namespace astra
