import json
import subprocess
import tomllib
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


def test_platformio_build_artifacts_are_ignored():
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "firmware/.pio/build/esp32dev/firmware.bin"],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert result.returncode == 0
