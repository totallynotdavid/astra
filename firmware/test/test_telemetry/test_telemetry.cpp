#include <unity.h>

#include "telemetry.h"

void setUp() {}
void tearDown() {}

void test_temperature_register_is_register_zero() {
  TEST_ASSERT_EQUAL_UINT8(0x00, astra::max30205::kTemperatureRegister);
  TEST_ASSERT_EQUAL_UINT8(0x01, astra::max30205::kConfigRegister);
}

void test_temperature_counts_to_celsius() {
  const uint8_t room[2] = {0x19, 0x00};
  const uint8_t body[2] = {0x24, 0x80};
  const uint8_t below_zero[2] = {0xFF, 0x00};
  TEST_ASSERT_EQUAL_FLOAT(25.0f, astra::temperatureCelsius(room));
  TEST_ASSERT_EQUAL_FLOAT(36.5f, astra::temperatureCelsius(body));
  TEST_ASSERT_EQUAL_FLOAT(-1.0f, astra::temperatureCelsius(below_zero));
}

void test_accel_magnitude_of_one_g() {
  const uint8_t flat[6] = {0x00, 0x00, 0x00, 0x00, 0x08, 0x00};
  const uint8_t tilted[6] = {0x08, 0x00, 0x00, 0x00, 0x00, 0x00};
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 9.80665f, astra::accelMagnitude(flat));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 9.80665f, astra::accelMagnitude(tilted));
}

void test_accel_data_register_is_the_first_x_byte() {
  TEST_ASSERT_EQUAL_UINT8(0x3B, astra::mpu6050::kAccelDataRegister);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_temperature_register_is_register_zero);
  RUN_TEST(test_temperature_counts_to_celsius);
  RUN_TEST(test_accel_magnitude_of_one_g);
  RUN_TEST(test_accel_data_register_is_the_first_x_byte);
  return UNITY_END();
}
