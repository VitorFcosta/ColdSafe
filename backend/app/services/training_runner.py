"""Fixed private subprocess entry point; never deserializes model pickle input."""
import json
from pathlib import Path
import sys


def main() -> None:
    phase, source, output, *context = sys.argv[1:]
    if phase == 'prepare':
        from backend.app.services.training_data import prepare_dataset
        data = json.loads(Path(context[0]).read_text())
        prepare_dataset(Path(source), data['dataset'], data['job'], Path(output), seed=42)
    elif phase == 'health':
        from backend.app.services.health_training import train_health
        train_health(Path(source), Path(output), seed=42)
    elif phase == 'rul':
        from backend.app.services.rul_training import train_rul
        train_rul(Path(source), Path(output), seed=42)
    else:
        raise ValueError('Unsupported training phase')


if __name__ == '__main__':
    main()
