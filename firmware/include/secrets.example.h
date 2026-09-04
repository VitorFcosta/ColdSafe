#pragma once

namespace coldsafe::secrets {

inline constexpr char WIFI_SSID[] = "Wokwi-GUEST";
inline constexpr char WIFI_PASSWORD[] = "";

inline constexpr char MQTT_HOST[] = "host.wokwi.internal";
inline constexpr int MQTT_PORT = 1883;
inline constexpr char MQTT_USERNAME[] = "coldsafe-device";
inline constexpr char MQTT_PASSWORD[] = "REPLACE_WITH_MQTT_DEVICE_PASSWORD";

inline constexpr char DEVICE_ID[] = "esp32-lab-01";

}  // namespace coldsafe::secrets
