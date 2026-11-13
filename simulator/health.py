"""Check progress recorded by the application's own loop, without extra threads."""
import argparse
import math
import os
from pathlib import Path
import time

HEARTBEAT = Path('/tmp/coldsafe-heartbeat')


def mark_healthy() -> None:
    if os.environ.get('COLDSAFE_HEALTHCHECK') == '1':
        HEARTBEAT.write_text(str(time.monotonic()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('max_age_seconds', type=float, nargs='?', default=30)
    args = parser.parse_args()
    if not math.isfinite(args.max_age_seconds) or args.max_age_seconds <= 0:
        parser.error('max_age_seconds must be finite and positive')
    try:
        recorded = float(HEARTBEAT.read_text())
        age = time.monotonic() - recorded
    except (OSError, ValueError):
        return 1
    return 0 if math.isfinite(recorded) and 0 <= age <= args.max_age_seconds else 1


if __name__ == '__main__':
    raise SystemExit(main())
