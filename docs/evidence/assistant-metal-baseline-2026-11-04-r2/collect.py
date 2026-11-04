"""Read-only baseline evidence; no service lifecycle or model requests."""

import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def stamp():
    return datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()


def command(args):
    started = stamp()
    result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(f"Read-only command failed: {args}: {result.stderr}")
    return {"command": args, "started_at": started, "finished_at": stamp(),
            "stdout": result.stdout}


def battery(text):
    match = re.search(r"(\d+)%;", text)
    if not match:
        raise ValueError("Battery percentage missing")
    return {"percent": int(match[1]), "on_battery": "'Battery Power'" in text,
            "warning": "Battery Warning:" in text}


def vm(text):
    size = re.search(r"page size of (\d+) bytes", text)
    if not size:
        raise ValueError("VM page size missing")
    pages = {key: int(value) for key, value in
             re.findall(r'^([^\n:]+):\s+(\d+)\.', text, re.MULTILINE)}
    for key in ("Pageins", "Pageouts", "Swapins", "Swapouts"):
        if key not in pages:
            raise ValueError(f"VM counter missing: {key}")
    return {"page_size_bytes": int(size[1]), "pages": pages}


def stop_reason(power, pressure, warning_since, elapsed):
    if not power["on_battery"]:
        return "power_source_changed"
    if power["warning"]:
        return "low_battery_warning"
    if pressure == 4:
        return "critical_memory_pressure"
    if pressure not in (1, 2):
        return "unknown_memory_pressure"
    if warning_since is not None and elapsed - warning_since >= 60:
        return "memory_warning_60_seconds"
    return None


def apps():
    raw = command(["/bin/ps", "-axo", "comm="])
    return {"started_at": raw["started_at"], "finished_at": raw["finished_at"],
            "method": "Process .app names only; includes background agents; no titles or arguments",
            "names": sorted(set(re.findall(r"/([^/\n]+\.app)/", raw["stdout"])))}


def services():
    return {"containers": command(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"]),
            "model_residency": command(["docker", "model", "ps"])}


def hashes():
    paths = [*ROOT.glob("compose*.yaml"),
             ROOT / "docs/evidence/assistant-metal-baseline-2026-11-04/README.md",
             ROOT / "docs/evidence/assistant-metal-baseline-2026-11-04/preflight.json"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}


def inventory():
    commands = {
        "hardware": ["/usr/sbin/sysctl", "machdep.cpu.brand_string", "hw.memsize"],
        "macos": ["/usr/bin/sw_vers"],
        "energy": ["/usr/bin/pmset", "-g", "custom"],
        "memory_pressure_query": ["/usr/bin/memory_pressure", "-Q"],
        "docker_capacity": ["docker", "info", "--format",
                            '{"memory_capacity_bytes":{{.MemTotal}},"cpus":{{.NCPU}},"server_version":{{json .ServerVersion}}}'],
        "docker_desktop": ["/usr/bin/defaults", "read", "/Applications/Docker.app/Contents/Info", "CFBundleShortVersionString"],
        "dmr_version": ["docker", "model", "version"],
        "dmr_status": ["docker", "model", "status"],
        "model_inventory": ["docker", "model", "list"],
        "containers_all": ["docker", "ps", "-a", "--no-trunc", "--format", "{{.ID}}\t{{.Names}}\t{{.Status}}"],
        "volumes": ["docker", "volume", "ls", "--filter", "name=coldsafe_", "--format", "{{.Name}}"],
        "git_head": ["git", "rev-parse", "HEAD"],
        "git_status": ["git", "status", "--short"],
    }
    result = {"started_at": stamp(), "commands": {k: command(v) for k, v in commands.items()},
              "apps": apps(), "hashes": hashes(), "services": services()}
    names = [line.split("\t")[0] for line in result["commands"]["containers_all"]["stdout"].splitlines()]
    if names:
        template = '{"id":{{json .Id}},"name":{{json .Name}},"image_id":{{json .Image}},"status":{{json .State.Status}},"oom_killed":{{.State.OOMKilled}},"exit_code":{{.State.ExitCode}},"memory_limit_bytes":{{.HostConfig.Memory}},"memory_swap_limit_bytes":{{.HostConfig.MemorySwap}},"nano_cpus":{{.HostConfig.NanoCpus}},"mounts":[{{range $i,$m := .Mounts}}{{if $i}},{{end}}{"type":{{json $m.Type}},"destination":{{json $m.Destination}}}{{end}}]}'
        result["container_metadata"] = command(["docker", "inspect", "--format", template, *names])
    result["finished_at"] = stamp()
    return result


def service_issue(state):
    if state["containers"]["stdout"].strip():
        return "running_container_detected"
    if len(state["model_residency"]["stdout"].strip().splitlines()) != 1:
        return "model_residency_detected_or_unrecognized"
    return None


def write_json(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def collect():
    if (HERE / "samples.jsonl").exists():
        raise RuntimeError("Existing collection preserved; choose a new evidence folder")
    before = inventory()
    write_json("inventory-before.json", before)
    outcome = {"status": "collecting", "started_at": stamp(), "duration_target_s": 900,
               "interval_target_s": 5, "samples": 0, "reason": service_issue(before["services"])}
    start = time.monotonic()
    warning_since = None
    previous_elapsed = None
    try:
        with (HERE / "samples.jsonl").open("x") as output:
            if outcome["reason"]:
                raise RuntimeError(outcome["reason"])
            for index in range(181):
                target = start + index * 5
                time.sleep(max(0, target - time.monotonic()))
                elapsed = time.monotonic() - start
                raw = {"battery": command(["/usr/bin/pmset", "-g", "batt"]),
                       "pressure": command(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"]),
                       "swap": command(["/usr/sbin/sysctl", "vm.swapusage"])}
                vm_time = time.monotonic()
                raw["vm_stat"] = command(["/usr/bin/vm_stat"])
                power = battery(raw["battery"]["stdout"])
                pressure = int(raw["pressure"]["stdout"].strip())
                if pressure == 2 and warning_since is None:
                    warning_since = elapsed
                if pressure != 2:
                    warning_since = None
                disk = __import__("os").statvfs(ROOT)
                sample = {"index": index, "timestamp": stamp(), "elapsed_s": elapsed,
                          "vm_elapsed_s": vm_time - start, "raw": raw,
                          "battery": power, "pressure": pressure, "vm": vm(raw["vm_stat"]["stdout"]),
                          "disk_available_bytes": disk.f_bavail * disk.f_frsize}
                reason = stop_reason(power, pressure, warning_since, elapsed)
                if previous_elapsed is not None and elapsed - previous_elapsed > 10:
                    reason = reason or "sampling_gap_over_10_seconds"
                if index % 6 == 0:
                    sample["services"] = services()
                    reason = reason or service_issue(sample["services"])
                    sample["energy"] = command(["/usr/bin/pmset", "-g", "custom"])
                    if sample["energy"]["stdout"] != before["commands"]["energy"]["stdout"]:
                        reason = reason or "energy_settings_changed"
                sample["stop_reason"] = reason
                output.write(json.dumps(sample, ensure_ascii=False) + "\n")
                output.flush()
                previous_elapsed = elapsed
                outcome["samples"] = index + 1
                if index % 12 == 0 or reason:
                    print(json.dumps({"elapsed_s": round(elapsed, 2), "samples": index + 1,
                                      "battery_percent": power["percent"], "pressure": pressure,
                                      "reason": reason}), flush=True)
                if reason:
                    outcome["reason"] = reason
                    break
            outcome["status"] = "completed" if outcome["samples"] == 181 and not outcome["reason"] else "interrupted"
    except Exception as error:
        outcome["status"] = "interrupted"
        outcome["reason"] = str(error)
    finally:
        outcome["finished_at"] = stamp()
        outcome["elapsed_s"] = time.monotonic() - start
        write_json("outcome.json", outcome)
    after = inventory()
    write_json("inventory-after.json", after)
    print(json.dumps(outcome), flush=True)


def self_test():
    good = battery("Now drawing from 'Battery Power'\n40%; discharging")
    assert stop_reason(good, 1, None, 0) is None
    assert stop_reason(battery("'AC Power'\n40%; charging"), 1, None, 0) == "power_source_changed"
    assert stop_reason(battery("'Battery Power'\n10%; Battery Warning: Early"), 1, None, 0) == "low_battery_warning"
    assert stop_reason(good, 4, None, 0) == "critical_memory_pressure"
    assert stop_reason(good, 2, 5, 64.99) is None
    assert stop_reason(good, 2, 5, 65) == "memory_warning_60_seconds"
    parsed = vm("Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPageins: 2.\nPageouts: 0.\nSwapins: 3.\nSwapouts: 1.\n")
    assert parsed["pages"]["Swapouts"] == 1 and parsed["page_size_bytes"] == 16384
    assert 16384 / 1048576 / 5 == 0.003125
    for invalid in ("", "page size of 16384 bytes"):
        try:
            vm(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid VM output accepted")
    print("Self-checks passed: parsers, missing counters, battery/power and memory stop rules, resolution")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif not sys.argv[1:]:
        collect()
    else:
        raise SystemExit("Usage: collect.py [--self-test]")
