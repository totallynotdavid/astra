# Firmware

The firmware runs on an ESP32 dev board. Every second it prints one
`DeviceSample` JSON line at 115200 baud. [contract.md](contract.md) defines the
line. The [simulator](simulator.md) prints the same lines without a board.

Build and flash from `firmware/` with [PlatformIO](https://platformio.org):

```sh
pio run
pio run -t upload
pio device monitor
pio test -e native
```

`pio test -e native` runs the register map and the unit conversions on the host.

[`platformio.ini`](../firmware/platformio.ini) pins the platform and the
libraries. The board has no SpO2 or radiation sensor, and the firmware reports
neither.

## Build flags

Set a flag with `PLATFORMIO_BUILD_FLAGS`:

```sh
PLATFORMIO_BUILD_FLAGS='-DASTRA_DEVICE_ID=\"astra-02\"' pio run -t upload
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `ASTRA_DEVICE_ID` | `"astra-01"` | The `device_id` of every line. |
| `ASTRA_PPG_CONTACT_IR` | `50000` | Mean IR level in a second at or above which the PPG has contact. |
| `ASTRA_MOTION_RANGE_M_S2` | `3.0` | Spread of acceleration magnitude in a second at or above which the second is a motion artifact. |

The two thresholds are starting values. Tune them on the wearer's wrist.

## Wiring

All three sensors share one I2C bus at 400 kHz and run at 3.3 V.

| Sensor | Pin on the sensor | ESP32 dev board |
| --- | --- | --- |
| all | `VIN` / `VCC` | `3V3` |
| all | `GND` | `GND` |
| all | `SDA` | `GPIO21` |
| all | `SCL` | `GPIO22` |

| Sensor | I2C address | Strapping |
| --- | --- | --- |
| MAX30102 | `0x57` | none |
| MAX30205 | `0x48` | `A0`, `A1` and `A2` to `GND` |
| MPU6050 | `0x68` | `AD0` to `GND` |

The MAX30102 `INT` pin and the MPU6050 `INT` pin stay unconnected. The
firmware polls.

## Where each field comes from

[`src/main.cpp`](../firmware/src/main.cpp) reads the sensors.
[`lib/telemetry/`](../firmware/lib/telemetry) averages, decides what is missing
and formats the line.

| Field | Source |
| --- | --- |
| `seq` | Counts lines from 0 at boot. |
| `uptime_ms` | `millis()` when the line is printed. |
| `heart_rate_bpm` | The MAX30102 IR channel read at 100 Hz. The SparkFun MAX3010x library's `checkForBeat` finds each beat, and the value is the mean of the last four beat-to-beat rates, rounded to whole bpm. Rates outside 40 to 200 bpm are dropped. |
| `contact_temperature_c` | The MAX30205 temperature register, read once per line, 0.00390625 °C per count. |
| `accel_min_m_s2`, `accel_max_m_s2`, `accel_mean_m_s2` | The MPU6050 at ±16 g, read every 20 ms (50 Hz). Each reading becomes the magnitude of the three axes in m/s². The line holds the minimum, maximum and mean of the second. |
| `quality.ppg_contact` | `ok` when the mean IR level of the second reaches `ASTRA_PPG_CONTACT_IR`, `lost` when it does not, `unknown` when the MAX30102 is absent or gave no data. |
| `quality.motion_artifact` | True when maximum minus minimum acceleration in the second reaches `ASTRA_MOTION_RANGE_M_S2`. Beats found in that second are dropped, so they do not enter the heart rate. |

## Missing values

A value the firmware cannot give is `null`, with a reason in `missing`.

| Reason | When |
| --- | --- |
| `not_present` | The sensor did not answer on the bus at boot or at the last 5-second retry. |
| `warming_up` | The heart rate has no beat yet, or no clean beat for 10 seconds. |
| `no_contact` | The heart rate when `ppg_contact` is `lost`. |
| `sensor_error` | A read failed, the MAX30102 sent no data in a second, or a value fell outside the range [contract.md](contract.md) allows. |

All three acceleration values share one reason. The firmware retries a sensor
that is not ready every 5 seconds, so a sensor plugged in late starts reporting
without a reboot.
