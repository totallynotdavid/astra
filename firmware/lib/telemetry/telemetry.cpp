#include "telemetry.h"

#include <math.h>
#include <stdio.h>

namespace astra {

Value Value::absent(Missing reason) { return Value{false, 0.0f, reason}; }

Value Value::within(float number, float low, float high) {
  if (!isfinite(number) || number < low || number > high) {
    return absent(Missing::SensorError);
  }
  return Value{true, number, Missing::None};
}

float temperatureCelsius(const uint8_t raw[2]) {
  const int16_t counts = static_cast<int16_t>((raw[0] << 8) | raw[1]);
  return counts * max30205::kCelsiusPerCount;
}

float accelMagnitude(const uint8_t raw[6]) {
  const float x = static_cast<int16_t>((raw[0] << 8) | raw[1]);
  const float y = static_cast<int16_t>((raw[2] << 8) | raw[3]);
  const float z = static_cast<int16_t>((raw[4] << 8) | raw[5]);
  return sqrtf(x * x + y * y + z * z) / mpu6050::kCountsPerG * mpu6050::kGravity;
}

namespace {

const char *missingName(Missing reason) {
  switch (reason) {
    case Missing::NoContact:
      return "no_contact";
    case Missing::WarmingUp:
      return "warming_up";
    case Missing::SensorError:
      return "sensor_error";
    case Missing::NotPresent:
      return "not_present";
    case Missing::None:
      break;
  }
  return "sensor_error";
}

const char *contactName(Contact contact) {
  switch (contact) {
    case Contact::Ok:
      return "ok";
    case Contact::Lost:
      return "lost";
    case Contact::Unknown:
      break;
  }
  return "unknown";
}

class Writer {
 public:
  Writer(char *out, size_t size) : out_(out), size_(size) {}

  void text(const char *value) {
    append(snprintf(out_ + used(), remaining(), "%s", value));
  }

  void number(const char *name, const Value &value, const char *format) {
    char body[24];
    if (value.valid) {
      snprintf(body, sizeof body, format, static_cast<double>(value.number));
    } else {
      snprintf(body, sizeof body, "null");
    }
    append(snprintf(out_ + used(), remaining(), "\"%s\":%s", name, body));
  }

  void count(const char *format, uint32_t value) {
    append(snprintf(out_ + used(), remaining(), format, static_cast<unsigned long>(value)));
  }

  void textField(const char *format, const char *value) {
    append(snprintf(out_ + used(), remaining(), format, value));
  }

  bool ok() const { return !overflow_; }
  size_t length() const { return length_; }

 private:
  size_t used() const { return overflow_ ? size_ : length_; }
  size_t remaining() const { return size_ - used(); }

  void append(int written) {
    if (written < 0 || static_cast<size_t>(written) >= remaining()) {
      overflow_ = true;
      return;
    }
    length_ += static_cast<size_t>(written);
  }

  char *out_;
  size_t size_;
  size_t length_ = 0;
  bool overflow_ = false;
};

}  // namespace

size_t formatLine(char *out, size_t size, const Sample &sample) {
  if (size == 0) {
    return 0;
  }
  Writer w(out, size);
  w.textField("{\"schema_version\":\"1.0\",\"device_id\":\"%s\",", sample.deviceId);
  w.count("\"seq\":%lu,", sample.seq);
  w.count("\"uptime_ms\":%lu,", sample.uptimeMs);
  w.text("\"sampling_rate_hz\":1,\"measurements\":{");
  w.number("heart_rate_bpm", sample.heartRate, "%.0f");
  w.text(",");
  w.number("contact_temperature_c", sample.temperature, "%.1f");
  w.text(",");
  w.number("accel_min_m_s2", sample.accelMin, "%.1f");
  w.text(",");
  w.number("accel_max_m_s2", sample.accelMax, "%.1f");
  w.text(",");
  w.number("accel_mean_m_s2", sample.accelMean, "%.1f");
  w.textField("},\"quality\":{\"ppg_contact\":\"%s\",", contactName(sample.contact));
  w.text(sample.motionArtifact ? "\"motion_artifact\":true}" : "\"motion_artifact\":false}");

  const struct {
    const char *name;
    const Value &value;
  } fields[] = {
      {"heart_rate_bpm", sample.heartRate},
      {"contact_temperature_c", sample.temperature},
      {"accel_min_m_s2", sample.accelMin},
      {"accel_max_m_s2", sample.accelMax},
      {"accel_mean_m_s2", sample.accelMean},
  };
  bool first = true;
  for (const auto &field : fields) {
    if (field.value.valid) {
      continue;
    }
    w.text(first ? ",\"missing\":{" : ",");
    first = false;
    char entry[64];
    snprintf(entry, sizeof entry, "\"%s\":\"%s\"", field.name, missingName(field.value.reason));
    w.text(entry);
  }
  if (!first) {
    w.text("}");
  }
  w.text("}");

  if (!w.ok()) {
    out[0] = '\0';
    return 0;
  }
  return w.length();
}

void AccelWindow::reset() {
  count_ = 0;
  min_ = 0.0f;
  max_ = 0.0f;
  sum_ = 0.0f;
}

void AccelWindow::add(float magnitude) {
  if (count_ == 0 || magnitude < min_) {
    min_ = magnitude;
  }
  if (count_ == 0 || magnitude > max_) {
    max_ = magnitude;
  }
  sum_ += magnitude;
  count_++;
}

bool AccelWindow::motionArtifact(float rangeThreshold) const {
  return count_ > 0 && (max_ - min_) >= rangeThreshold;
}

void BeatAverager::clear() {
  hasLastBeat_ = false;
  rateCount_ = 0;
  rateNext_ = 0;
  pendingCount_ = 0;
}

void BeatAverager::beat(uint32_t nowMs) {
  if (hasLastBeat_) {
    const uint32_t interval = nowMs - lastBeatMs_;
    if (interval > 0) {
      const float rate = 60000.0f / static_cast<float>(interval);
      if (rate >= 40.0f && rate <= 200.0f && pendingCount_ < kPending) {
        pending_[pendingCount_++] = static_cast<uint8_t>(rate + 0.5f);
      }
    }
  }
  hasLastBeat_ = true;
  lastBeatMs_ = nowMs;
}

void BeatAverager::endSecond(bool motionArtifact, uint32_t nowMs) {
  if (!motionArtifact && pendingCount_ > 0) {
    for (size_t i = 0; i < pendingCount_; i++) {
      rates_[rateNext_] = pending_[i];
      rateNext_ = (rateNext_ + 1) % kRates;
      if (rateCount_ < kRates) {
        rateCount_++;
      }
    }
    lastCommitMs_ = nowMs;
  }
  pendingCount_ = 0;
}

bool BeatAverager::bpm(uint32_t nowMs, float &out) const {
  if (rateCount_ == 0 || nowMs - lastCommitMs_ > kStaleMs) {
    return false;
  }
  float sum = 0.0f;
  for (size_t i = 0; i < rateCount_; i++) {
    sum += rates_[i];
  }
  out = sum / static_cast<float>(rateCount_);
  return true;
}

}  // namespace astra
