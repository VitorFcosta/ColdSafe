import json
import subprocess
import tomllib
from configparser import ConfigParser
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIRMWARE_ROOT = REPOSITORY_ROOT / "firmware"


def test_platformio_target_and_sensor_library_are_pinned():
    configuration = (FIRMWARE_ROOT / "platformio.ini").read_text(encoding="utf-8")

    assert "platform = espressif32@7.0.1" in configuration
    assert "board = esp32dev" in configuration
    assert "framework = arduino" in configuration
    assert "monitor_speed = 115200" in configuration
    assert "beegee-tokyo/DHT sensor library for ESPx@1.19" in configuration
    assert "256dpi/MQTT@2.5.3" in configuration
    assert "bblanchon/ArduinoJson@7.4.3" in configuration
    assert "build_unflags = -std=gnu++11" in configuration
    assert "build_flags = -std=gnu++17" in configuration


def test_firmware_reads_dht22_and_writes_serial_measurements():
    source = (FIRMWARE_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")

    assert "#include <DHTesp.h>" in source
    assert "constexpr std::uint8_t dht_pin{15};" in source
    assert "dht_sensor.setup(dht_pin, DHTesp::DHT22);" in source
    assert "dht_sensor.getTempAndHumidity()" in source
    assert "temperature_c=%.1f humidity_percent=%.1f" in source

    serial_start = source.index("Serial.begin(115200);")
    boot_message = source.index('Serial.println("ColdSafe: firmware iniciado");')
    sensor_setup = source.index("dht_sensor.setup(dht_pin, DHTesp::DHT22);")

    assert serial_start < boot_message < sensor_setup
    assert "delay(500);" in source[serial_start:boot_message]


def test_firmware_configures_mqtt_broker_through_wokwi_gateway():
    source = (FIRMWARE_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")

    assert "#include <WiFi.h>" in source
    assert "#include <MQTT.h>" in source
    assert '#include "secrets.h"' in source
    assert "WiFi.mode(WIFI_STA);" in source
    assert (
        "WiFi.begin(coldsafe::secrets::WIFI_SSID, "
        "coldsafe::secrets::WIFI_PASSWORD, 6);"
    ) in source
    assert "WiFi.status() != WL_CONNECTED" in source
    assert "WiFiClient network_client;" in source
    assert "mqtt_client.begin(" in source
    assert "coldsafe::secrets::MQTT_HOST" in source
    assert "coldsafe::secrets::MQTT_PORT" in source


def test_firmware_publishes_v2_telemetry_and_handles_correlated_commands():
    source = (FIRMWARE_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")

    assert "#include <MQTT.h>" in source
    assert '"coldsafe/v2/devices/%s/telemetry"' in source
    assert '"coldsafe/v2/devices/%s/commands"' in source
    assert '"coldsafe/v2/devices/%s/acks"' in source
    assert "constexpr int mqtt_qos{1};" in source
    assert "constexpr unsigned long publish_interval_ms{5000UL};" in source
    assert "WiFiClient network_client;" in source
    assert "MQTTClient mqtt_client" in source
    assert "mqtt_client.begin(" in source
    assert "coldsafe::secrets::MQTT_HOST" in source
    assert "coldsafe::secrets::MQTT_PORT" in source
    assert "mqtt_client.connect(" in source
    assert "coldsafe::secrets::MQTT_PASSWORD" in source
    assert "mqtt_client.subscribe(command_topic, mqtt_qos)" in source
    assert "mqtt_client.onMessage(on_mqtt_message)" in source
    assert "valid_uuid(command_id)" in source
    assert "for (const auto& previous : ack_history)" in source
    assert "mqtt_client.loop();" in source
    assert '\\"schema_version\\":2' in source
    assert '\\"device_id\\":\\"%s\\"' in source
    assert '\\"temperature_c\\":%.1f' in source
    assert '\\"humidity_percent\\":%.1f' in source
    assert '\\"light_percent\\":%.1f' in source
    assert "mqtt_client.publish(telemetry_topic, payload, false, mqtt_qos)" in source
    assert "mqtt_client.publish(ack_topic, payload, false, mqtt_qos)" in source
    assert "delay(reading_interval_ms);" not in source


def test_wokwi_diagram_connects_dht22_to_esp32_gpio_15():
    diagram = json.loads((FIRMWARE_ROOT / "diagram.json").read_text(encoding="utf-8"))
    parts = {part["id"]: part for part in diagram["parts"]}
    connections = {
        frozenset((source, target))
        for source, target, _color, _route in diagram["connections"]
    }

    assert parts["esp32"]["type"] == "board-esp32-devkit-c-v4"
    assert parts["dht22"]["type"] == "wokwi-dht22"
    assert parts["dht22"]["attrs"] == {"temperature": "5.4", "humidity": "62.1"}
    assert frozenset(("esp32:3V3", "dht22:VCC")) in connections
    assert frozenset(("esp32:GND.1", "dht22:GND")) in connections
    assert frozenset(("esp32:15", "dht22:SDA")) in connections
    assert frozenset(("esp32:TX", "$serialMonitor:RX")) in connections
    assert frozenset(("esp32:RX", "$serialMonitor:TX")) in connections
    assert parts["light"]["type"] == "wokwi-photoresistor-sensor"
    assert parts["buzzer"]["type"] == "wokwi-buzzer"
    assert parts["led"]["type"] == "wokwi-led"
    assert parts["led_resistor"]["attrs"]["value"] == "220"
    for pair in (
        ("esp32:34", "light:AO"),
        ("esp32:19", "buzzer:2"),
        ("esp32:18", "led_resistor:1"),
        ("led_resistor:2", "led:A"),
        ("esp32:GND.1", "led:C"),
    ):
        assert frozenset(pair) in connections


def test_wokwi_serial_monitor_is_always_visible():
    diagram = json.loads((FIRMWARE_ROOT / "diagram.json").read_text(encoding="utf-8"))

    assert diagram["serialMonitor"] == {
        "display": "terminal",
        "newline": "lf",
        "convertEol": True,
    }


def test_wokwi_uses_platformio_build_artifacts():
    configuration = tomllib.loads(
        (FIRMWARE_ROOT / "wokwi.toml").read_text(encoding="utf-8")
    )

    assert configuration["wokwi"] == {
        "version": 1,
        "firmware": ".pio/build/esp32dev/firmware.bin",
        "elf": ".pio/build/esp32dev/firmware.elf",
        "rfc2217ServerPort": 4000,
    }


def test_two_wokwi_projects_use_distinct_firmware_and_mqtt_ids():
    platformio = ConfigParser(interpolation=None)
    platformio.read(FIRMWARE_ROOT / "platformio.ini", encoding="utf-8")
    first = platformio["env:esp32dev"]
    second = platformio["env:esp32dev-02"]
    assert 'COLDSAFE_DEVICE_ID="esp32-lab-01"' in first["build_flags"]
    assert 'COLDSAFE_DEVICE_ID="esp32-lab-02"' in second["build_flags"]

    first_wokwi = tomllib.loads((FIRMWARE_ROOT / "wokwi.toml").read_text())['wokwi']
    second_root = FIRMWARE_ROOT / "device-02"
    second_wokwi = tomllib.loads((second_root / "wokwi.toml").read_text())['wokwi']
    assert first_wokwi["rfc2217ServerPort"] != second_wokwi["rfc2217ServerPort"]
    assert second_root.joinpath(second_wokwi["firmware"]).resolve() == (
        FIRMWARE_ROOT / ".pio/build/esp32dev-02/firmware.bin"
    )
    assert second_root.joinpath(second_wokwi["elf"]).resolve() == (
        FIRMWARE_ROOT / ".pio/build/esp32dev-02/firmware.elf"
    )
    assert json.loads((second_root / "diagram.json").read_text()) == json.loads(
        (FIRMWARE_ROOT / "diagram.json").read_text()
    )

    source = (FIRMWARE_ROOT / "src/main.cpp").read_text()
    assert "mqtt_client.connect(device_id, mqtt_username, mqtt_password)" in source
    assert "device_id, latest_reading.temperature" in source


def test_platformio_build_artifacts_are_ignored():
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "firmware/.pio/build/esp32dev/firmware.bin"],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert result.returncode == 0
