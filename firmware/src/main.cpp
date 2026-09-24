#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHTesp.h>
#include <MQTT.h>
#include <WiFi.h>

#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>

#include "secrets.h"

namespace {

constexpr std::uint8_t dht_pin{15};
constexpr std::uint8_t light_pin{34};  // ADC1 works while Wi-Fi is active.
constexpr std::uint8_t led_pin{18};
constexpr std::uint8_t buzzer_pin{19};
constexpr unsigned long reading_interval_ms{2000UL};
constexpr unsigned long publish_interval_ms{5000UL};
constexpr unsigned long connection_retry_interval_ms{5000UL};
constexpr int mqtt_qos{1};
constexpr std::size_t payload_buffer_size{256U};
constexpr std::size_t topic_buffer_size{128U};
// ponytail: Recent QoS 1 retries fit in RAM; persist command IDs if replay across reboots matters.
constexpr std::size_t ack_history_size{8U};
// ponytail: Tune these ADC endpoints for physical sensors; Wokwi uses the full 12-bit range.
constexpr float light_adc_dark{4095.0F};
constexpr float light_adc_bright{0.0F};

#ifndef COLDSAFE_DEVICE_ID
#define COLDSAFE_DEVICE_ID coldsafe::secrets::DEVICE_ID
#endif
#ifndef COLDSAFE_MQTT_USERNAME
#define COLDSAFE_MQTT_USERNAME coldsafe::secrets::MQTT_USERNAME
#endif
constexpr const char* device_id{COLDSAFE_DEVICE_ID};
constexpr const char* mqtt_username{COLDSAFE_MQTT_USERNAME};
#ifdef COLDSAFE_DEVICE_02
#ifdef COLDSAFE_DEVICE_02_PASSWORD_CONFIGURED
constexpr const char* mqtt_password{coldsafe::secrets::MQTT_DEVICE_02_PASSWORD};
#else
// Existing local secrets.h still builds; configure the second password before connecting it.
constexpr const char* mqtt_password{coldsafe::secrets::MQTT_PASSWORD};
#endif
#else
constexpr const char* mqtt_password{coldsafe::secrets::MQTT_PASSWORD};
#endif

struct AckHistoryEntry {
    char command_id[37]{};
    char actuator[7]{};
    bool applied_state{false};
};

DHTesp dht_sensor;
WiFiClient network_client;
MQTTClient mqtt_client{512};
AckHistoryEntry ack_history[ack_history_size]{};
std::size_t next_ack_slot{0U};
char telemetry_topic[topic_buffer_size]{};
char command_topic[topic_buffer_size]{};
char ack_topic[topic_buffer_size]{};
bool wifi_connected_reported{false};
bool has_valid_reading{false};
TempAndHumidity latest_reading{};
float latest_light_percent{0.0F};
unsigned long last_wifi_attempt_ms{0UL};
unsigned long last_mqtt_attempt_ms{0UL};
unsigned long last_reading_ms{0UL};
unsigned long last_publish_ms{0UL};

bool interval_elapsed(const unsigned long now, const unsigned long previous,
                      const unsigned long interval) {
    return previous == 0UL || now - previous >= interval;
}

bool valid_uuid(const char* value) {
    if (value == nullptr || std::strlen(value) != 36U) return false;
    for (std::size_t index = 0; index < 36U; ++index) {
        const char character = value[index];
        if (index == 8U || index == 13U || index == 18U || index == 23U) {
            if (character != '-') return false;
        } else if (!((character >= '0' && character <= '9') ||
                     (character >= 'a' && character <= 'f') ||
                     (character >= 'A' && character <= 'F'))) {
            return false;
        }
    }
    return true;
}

bool publish_ack(const char* command_id, const char* actuator,
                 const bool applied, const bool applied_state) {
    char payload[payload_buffer_size]{};
    const int length = applied
        ? std::snprintf(payload, sizeof(payload),
            "{\"schema_version\":2,\"command_id\":\"%s\",\"device_id\":\"%s\","
            "\"actuator\":\"%s\",\"result\":\"applied\",\"applied_state\":%s}",
            command_id, device_id, actuator, applied_state ? "true" : "false")
        : std::snprintf(payload, sizeof(payload),
            "{\"schema_version\":2,\"command_id\":\"%s\",\"device_id\":\"%s\","
            "\"actuator\":\"%s\",\"result\":\"rejected\",\"applied_state\":null,"
            "\"reason\":\"INVALID_COMMAND\"}", command_id, device_id, actuator);
    if (length < 0 || static_cast<std::size_t>(length) >= sizeof(payload)) return false;
    return mqtt_client.publish(ack_topic, payload, false, mqtt_qos);
}

void on_mqtt_message(String& topic, String& payload) {
    if (topic != command_topic || payload.length() > 512U) return;

    JsonDocument document;
    if (deserializeJson(document, payload) != DeserializationError::Ok ||
        !document.is<JsonObject>()) {
        Serial.println("ColdSafe: comando JSON invalido");
        return;
    }
    const JsonObject command = document.as<JsonObject>();
    const char* command_id = command["command_id"].as<const char*>();
    const char* actuator = command["actuator"].as<const char*>();
    const char* target = command["device_id"].as<const char*>();
    if (!valid_uuid(command_id) || actuator == nullptr ||
        (std::strcmp(actuator, "led") != 0 && std::strcmp(actuator, "buzzer") != 0) ||
        target == nullptr || std::strcmp(target, device_id) != 0) {
        Serial.println("ColdSafe: comando sem correlacao ou destino valido");
        return;
    }

    for (const auto& previous : ack_history) {
        if (std::strcmp(previous.command_id, command_id) == 0) {
            publish_ack(command_id, previous.actuator, true, previous.applied_state);
            Serial.println("ColdSafe: comando duplicado; confirmacao reenviada");
            return;
        }
    }

    const char* source = command["source"].as<const char*>();
    const char* issued_at = command["issued_at"].as<const char*>();
    const bool valid = command.size() == 7U &&
        command["schema_version"].is<int>() && command["schema_version"].as<int>() == 2 &&
        command["desired_state"].is<bool>() && source != nullptr && issued_at != nullptr &&
        std::strlen(issued_at) >= 20U && std::strlen(issued_at) <= 35U &&
        issued_at[10] == 'T' &&
        ((std::strcmp(actuator, "led") == 0 && std::strcmp(source, "manual") == 0) ||
         (std::strcmp(actuator, "buzzer") == 0 && std::strcmp(source, "automatic") == 0));
    if (!valid) {
        publish_ack(command_id, actuator, false, false);
        Serial.println("ColdSafe: comando rejeitado");
        return;
    }

    const bool desired_state = command["desired_state"].as<bool>();
    if (std::strcmp(actuator, "led") == 0) {
        digitalWrite(led_pin, desired_state ? HIGH : LOW);
    } else if (desired_state) {
        tone(buzzer_pin, 1000);
    } else {
        noTone(buzzer_pin);
    }

    AckHistoryEntry& stored = ack_history[next_ack_slot];
    std::strcpy(stored.command_id, command_id);
    std::strcpy(stored.actuator, actuator);
    stored.applied_state = desired_state;
    next_ack_slot = (next_ack_slot + 1U) % ack_history_size;
    if (!publish_ack(command_id, actuator, true, desired_state)) {
        Serial.println("ColdSafe: falha ao publicar confirmacao MQTT");
    }
    Serial.printf("ColdSafe: %s %s\n", actuator, desired_state ? "ligado" : "desligado");
}

void start_wifi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(coldsafe::secrets::WIFI_SSID, coldsafe::secrets::WIFI_PASSWORD, 6);
    last_wifi_attempt_ms = millis();
    Serial.println("ColdSafe: conectando ao Wi-Fi do Wokwi");
}

void maintain_wifi(const unsigned long now) {
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
    if (!interval_elapsed(now, last_wifi_attempt_ms, connection_retry_interval_ms)) return;
    last_wifi_attempt_ms = now;
    Serial.println("ColdSafe: tentando reconectar ao Wi-Fi");
    WiFi.reconnect();
}

void maintain_mqtt(const unsigned long now) {
    if (WiFi.status() != WL_CONNECTED || mqtt_client.connected()) return;
    if (!interval_elapsed(now, last_mqtt_attempt_ms, connection_retry_interval_ms)) return;
    last_mqtt_attempt_ms = now;
    Serial.println("ColdSafe: tentando conectar ao MQTT");
    if (!mqtt_client.connect(device_id, mqtt_username, mqtt_password)) {
        Serial.println("ColdSafe: conexao MQTT falhou; nova tentativa em 5 s");
        return;
    }
    if (!mqtt_client.subscribe(command_topic, mqtt_qos)) {
        Serial.println("ColdSafe: falha ao assinar comandos MQTT");
        mqtt_client.disconnect();
        return;
    }
    Serial.println("ColdSafe: MQTT conectado e comandos assinados");
}

void sample_sensor(const unsigned long now) {
    if (!interval_elapsed(now, last_reading_ms, reading_interval_ms)) return;
    last_reading_ms = now;

    const TempAndHumidity reading{dht_sensor.getTempAndHumidity()};
    const int light_raw = analogRead(light_pin);
    has_valid_reading = std::isfinite(reading.temperature) &&
        reading.temperature >= -40.0F && reading.temperature <= 80.0F &&
        std::isfinite(reading.humidity) && reading.humidity >= 0.0F &&
        reading.humidity <= 100.0F && light_raw >= 0 && light_raw <= 4095;
    if (!has_valid_reading) {
        Serial.println("ColdSafe: leitura invalida descartada");
        return;
    }
    latest_reading = reading;
    latest_light_percent = (light_adc_dark - light_raw) * 100.0F /
                           (light_adc_dark - light_adc_bright);
    Serial.printf("temperature_c=%.1f humidity_percent=%.1f light_percent=%.1f\n",
                  reading.temperature, reading.humidity, latest_light_percent);
}

void publish_telemetry(const unsigned long now) {
    if (!mqtt_client.connected() || !has_valid_reading ||
        !interval_elapsed(now, last_publish_ms, publish_interval_ms)) return;
    last_publish_ms = now;

    char payload[payload_buffer_size]{};
    const int length = std::snprintf(
        payload, sizeof(payload),
        "{\"schema_version\":2,\"device_id\":\"%s\",\"temperature_c\":%.1f,"
        "\"humidity_percent\":%.1f,\"light_percent\":%.1f}",
        device_id, latest_reading.temperature, latest_reading.humidity, latest_light_percent
    );
    if (length < 0 || static_cast<std::size_t>(length) >= sizeof(payload)) {
        Serial.println("ColdSafe: payload MQTT excedeu o buffer");
        return;
    }
    if (mqtt_client.publish(telemetry_topic, payload, false, mqtt_qos)) {
        Serial.printf("ColdSafe: telemetria publicada em %s com QoS %d\n",
                      telemetry_topic, mqtt_qos);
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
    analogReadResolution(12);
    pinMode(light_pin, INPUT);
    pinMode(led_pin, OUTPUT);
    pinMode(buzzer_pin, OUTPUT);
    digitalWrite(led_pin, LOW);
    noTone(buzzer_pin);

    std::snprintf(telemetry_topic, sizeof(telemetry_topic),
                  "coldsafe/v2/devices/%s/telemetry", device_id);
    std::snprintf(command_topic, sizeof(command_topic),
                  "coldsafe/v2/devices/%s/commands", device_id);
    std::snprintf(ack_topic, sizeof(ack_topic),
                  "coldsafe/v2/devices/%s/acks", device_id);
    mqtt_client.begin(coldsafe::secrets::MQTT_HOST, coldsafe::secrets::MQTT_PORT,
                      network_client);
    mqtt_client.onMessage(on_mqtt_message);
    start_wifi();
}

void loop() {
    const unsigned long now{millis()};
    maintain_wifi(now);
    maintain_mqtt(now);
    mqtt_client.loop();
    sample_sensor(now);
    publish_telemetry(now);
    delay(10);
}
