#include <Arduino.h>
#include <DHTesp.h>
#include <WiFi.h>

#include <cmath>
#include <cstdint>

#include "secrets.h"

namespace {

constexpr std::uint8_t dht_pin{15};
constexpr unsigned long reading_interval_ms{2000UL};
constexpr unsigned long gateway_probe_retry_interval_ms{5000UL};

DHTesp dht_sensor;
WiFiClient gateway_probe;
bool broker_reachable{false};
bool wifi_connected_reported{false};
unsigned long last_gateway_probe_ms{0UL};

void start_wifi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(coldsafe::secrets::WIFI_SSID, coldsafe::secrets::WIFI_PASSWORD, 6);
    Serial.println("ColdSafe: conectando ao Wi-Fi do Wokwi");
}

void probe_local_broker() {
    if (broker_reachable || WiFi.status() != WL_CONNECTED) {
        return;
    }

    if (!wifi_connected_reported) {
        Serial.print("ColdSafe: Wi-Fi conectado, IP ");
        Serial.println(WiFi.localIP());
        wifi_connected_reported = true;
    }

    const unsigned long current_time_ms{millis()};
    if (last_gateway_probe_ms != 0UL &&
        current_time_ms - last_gateway_probe_ms < gateway_probe_retry_interval_ms) {
        return;
    }
    last_gateway_probe_ms = current_time_ms;

    const bool connected{gateway_probe.connect(
        coldsafe::secrets::MQTT_HOST,
        coldsafe::secrets::MQTT_PORT
    )};
    if (connected) {
        Serial.println("ColdSafe: gateway do Wokwi e Mosquitto local acessiveis");
        broker_reachable = true;
    } else {
        Serial.println("ColdSafe: Mosquitto ainda nao acessivel pelo gateway");
    }
    gateway_probe.stop();
}

void print_reading(const TempAndHumidity& reading) {
    Serial.printf(
        "temperature_c=%.1f humidity_percent=%.1f\n",
        reading.temperature,
        reading.humidity
    );
}

}  // namespace

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("ColdSafe: firmware iniciado");

    dht_sensor.setup(dht_pin, DHTesp::DHT22);
    Serial.println("ColdSafe: DHT22 inicializado no GPIO 15");

    start_wifi();
}

void loop() {
    probe_local_broker();

    const TempAndHumidity reading{dht_sensor.getTempAndHumidity()};

    if (!std::isfinite(reading.temperature) || !std::isfinite(reading.humidity)) {
        Serial.printf("Falha na leitura do DHT22: %s\n", dht_sensor.getStatusString());
    } else {
        print_reading(reading);
    }

    delay(reading_interval_ms);
}
