#pragma once

// Define in local secrets.h when the second device has its own password.
#define COLDSAFE_DEVICE_02_PASSWORD_CONFIGURED

namespace coldsafe::secrets {

inline constexpr char WIFI_SSID[] = "Wokwi-GUEST";
inline constexpr char WIFI_PASSWORD[] = "";

inline constexpr char MQTT_HOST[] = "host.wokwi.internal";
inline constexpr int MQTT_PORT = 1883;
inline constexpr char MQTT_USERNAME[] = "coldsafe-device";
// Copy to secrets.h and populate both passwords locally. Never commit that file.
inline constexpr char MQTT_PASSWORD[] = "REPLACE_WITH_MQTT_DEVICE_PASSWORD";
inline constexpr char MQTT_DEVICE_02_PASSWORD[] = "REPLACE_WITH_MQTT_DEVICE_02_PASSWORD";

inline constexpr char DEVICE_ID[] = "esp32-lab-01";

}  // namespace coldsafe::secrets
