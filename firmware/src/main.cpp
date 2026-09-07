#include <Arduino.h>
#include <DHTesp.h>
#include <MQTT.h>
#include <WiFi.h>

#include <cmath>
#include <cstdio>
#include <cstdint>

#include "secrets.h"

namespace {

constexpr std::uint8_t dht_pin{15};
constexpr unsigned long reading_interval_ms{2000UL};
constexpr unsigned long publish_interval_ms{5000UL};
constexpr unsigned long connection_retry_interval_ms{5000UL};
constexpr char mqtt_topic[]{"coldsafe/v1/telemetry"};
constexpr int mqtt_qos{1};
constexpr std::size_t payload_buffer_size{192U};

DHTesp dht_sensor;
WiFiClient network_client;
MQTTClient mqtt_client{256};
bool wifi_connected_reported{false};
bool mqtt_connected_reported{false};
bool has_valid_reading{false};
TempAndHumidity latest_reading{};
unsigned long last_wifi_attempt_ms{0UL};
unsigned long last_mqtt_attempt_ms{0UL};
unsigned long last_reading_ms{0UL};
unsigned long last_publish_ms{0UL};

bool interval_elapsed(
    const unsigned long current_time_ms,
    const unsigned long previous_time_ms,
    const unsigned long interval_ms
) {
    return previous_time_ms == 0UL ||
           current_time_ms - previous_time_ms >= interval_ms;
}

void start_wifi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(coldsafe::secrets::WIFI_SSID, coldsafe::secrets::WIFI_PASSWORD, 6);
    last_wifi_attempt_ms = millis();
    Serial.println("ColdSafe: conectando ao Wi-Fi do Wokwi");
}

void maintain_wifi(const unsigned long current_time_ms) {
    if (WiFi.status() == WL_CONNECTED) {
        if (!wifi_connected_reported) {
            Serial.print("ColdSafe: Wi-Fi conectado, IP ");
            Serial.println(WiFi.localIP());
            wifi_connected_reported = true;
        }
        return;
    }

    if (wifi_connected_reported) {
        Serial.println("ColdSafe: Wi-Fi desconectado");
        wifi_connected_reported = false;
    }

    if (!interval_elapsed(
            current_time_ms,
            last_wifi_attempt_ms,
            connection_retry_interval_ms
        )) {
        return;
    }

    last_wifi_attempt_ms = current_time_ms;
    Serial.println("ColdSafe: tentando reconectar ao Wi-Fi");
    WiFi.reconnect();
}

void maintain_mqtt(const unsigned long current_time_ms) {
    if (WiFi.status() != WL_CONNECTED) {
        mqtt_connected_reported = false;
        return;
    }

    if (mqtt_client.connected()) {
        if (!mqtt_connected_reported) {
            Serial.println("ColdSafe: MQTT conectado ao Mosquitto local");
            mqtt_connected_reported = true;
        }
        return;
    }

    mqtt_connected_reported = false;
    if (!interval_elapsed(
            current_time_ms,
            last_mqtt_attempt_ms,
            connection_retry_interval_ms
        )) {
        return;
    }

    last_mqtt_attempt_ms = current_time_ms;
    Serial.println("ColdSafe: tentando conectar ao MQTT");
    if (!mqtt_client.connect(
            coldsafe::secrets::DEVICE_ID,
            coldsafe::secrets::MQTT_USERNAME,
            coldsafe::secrets::MQTT_PASSWORD
        )) {
        Serial.println("ColdSafe: conexao MQTT falhou; nova tentativa em 5 s");
    }
}

void print_reading(const TempAndHumidity& reading) {
    Serial.printf(
        "temperature_c=%.1f humidity_percent=%.1f\n",
        reading.temperature,
        reading.humidity
    );
}

void sample_sensor(const unsigned long current_time_ms) {
    if (!interval_elapsed(current_time_ms, last_reading_ms, reading_interval_ms)) {
        return;
    }
    last_reading_ms = current_time_ms;

    const TempAndHumidity reading{dht_sensor.getTempAndHumidity()};
    if (!std::isfinite(reading.temperature) || !std::isfinite(reading.humidity)) {
        Serial.printf("Falha na leitura do DHT22: %s\n", dht_sensor.getStatusString());
        return;
    }

    latest_reading = reading;
    has_valid_reading = true;
    print_reading(reading);
}

void publish_telemetry(const unsigned long current_time_ms) {
    if (!mqtt_client.connected() || !has_valid_reading ||
        !interval_elapsed(current_time_ms, last_publish_ms, publish_interval_ms)) {
        return;
    }
    last_publish_ms = current_time_ms;

    char payload[payload_buffer_size]{};
    const int payload_length{std::snprintf(
        payload,
        sizeof(payload),
        "{\"schema_version\":1,\"device_id\":\"%s\",\"temperature_c\":%.1f,"
        "\"humidity_percent\":%.1f}",
        coldsafe::secrets::DEVICE_ID,
        latest_reading.temperature,
        latest_reading.humidity
    )};
    if (payload_length < 0 ||
        static_cast<std::size_t>(payload_length) >= sizeof(payload)) {
        Serial.println("ColdSafe: payload MQTT excedeu o buffer");
        return;
    }

    if (mqtt_client.publish(mqtt_topic, payload, false, mqtt_qos)) {
        Serial.printf("ColdSafe: telemetria publicada em %s com QoS %d\n", mqtt_topic, mqtt_qos);
    } else {
        Serial.println("ColdSafe: falha ao publicar telemetria MQTT");
    }
}

}  // namespace

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("ColdSafe: firmware iniciado");

    dht_sensor.setup(dht_pin, DHTesp::DHT22);
    Serial.println("ColdSafe: DHT22 inicializado no GPIO 15");

    mqtt_client.begin(
        coldsafe::secrets::MQTT_HOST,
        coldsafe::secrets::MQTT_PORT,
        network_client
    );
    start_wifi();
}

void loop() {
    const unsigned long current_time_ms{millis()};
    maintain_wifi(current_time_ms);
    maintain_mqtt(current_time_ms);
    mqtt_client.loop();
    sample_sensor(current_time_ms);
    publish_telemetry(current_time_ms);
    delay(10);
}
