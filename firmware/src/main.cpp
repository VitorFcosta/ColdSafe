#include <Arduino.h>
#include <DHTesp.h>

#include <cmath>
#include <cstdint>

namespace {

constexpr std::uint8_t dht_pin{15};
constexpr unsigned long reading_interval_ms{2000UL};

DHTesp dht_sensor;

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
}

void loop() {
    const TempAndHumidity reading{dht_sensor.getTempAndHumidity()};

    if (!std::isfinite(reading.temperature) || !std::isfinite(reading.humidity)) {
        Serial.printf("Falha na leitura do DHT22: %s\n", dht_sensor.getStatusString());
    } else {
        print_reading(reading);
    }

    delay(reading_interval_ms);
}
