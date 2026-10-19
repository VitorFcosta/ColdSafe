"""Load registered worker packages after JSON, hash and runtime validation."""
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
from pathlib import Path
import pickle
import platform
from uuid import UUID

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from backend.app.domain.feature_preprocessing import FeatureTransform
from backend.app.domain.features import FeatureSpec
from backend.app.services.datasets import _internal_file
from backend.app.services.health_training import _manifest
from backend.app.services.training_results import _json, read_training_result, TrainingResultUnavailable


class ModelBundleUnavailable(Exception):
    """A private bundle cannot safely be activated."""


@dataclass(frozen=True)
class LoadedBundle:
    model_id: UUID
    model_version: str
    features_version: str
    health: HistGradientBoostingRegressor
    rul: HistGradientBoostingRegressor
    spec: FeatureSpec
    transform: FeatureTransform
    units: dict[str, str]


def _runtime_matches(versions: dict[str, str]) -> bool:
    expected = {'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__,
        **{name: version(name) for name in ('scipy', 'joblib', 'threadpoolctl', 'narwhals', 'cloudpickle')}}
    # Python patch releases preserve pickle compatibility; numerical libraries require the exact training version.
    return (set(versions) == set(expected) and
        versions['python'].split('.')[:2] == expected['python'].split('.')[:2] and
        all(versions[name] == value for name, value in expected.items() if name != 'python'))


def load_model_bundle(root: Path, model: dict, job: dict, dataset: dict) -> LoadedBundle:
    """Accept only private model/job/dataset records resolved by the service.

    Hashes detect damage, not malicious producers: pickle remains trusted worker
    output, never a public upload or a caller-supplied filesystem path.
    """
    try:
        result = read_training_result(root, model, job, dataset)
        if not result['eligible'] or not _runtime_matches(result['versions']):
            raise ValueError('Ineligible model or incompatible runtime')
        directory = _internal_file(root.resolve(strict=True), model['artifact_key']).parent
        _, spec, transform = _manifest(directory / 'prepared')
        reports = {target: _json(directory, f'{target}/report.json') for target in ('health', 'rul')}
        loaded = {}
        for target in ('health', 'rul'):
            path = _internal_file(directory, f'{target}/model.pkl')
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != reports[target]['model_sha256']:
                raise ValueError('Model changed after validation')
            payload = pickle.loads(content)
            keys = {'model', 'transform', 'spec', 'features_version', 'prediction_range'}
            if target == 'rul':
                keys |= {'target', 'unit'}
            if (type(payload) is not dict or set(payload) != keys or
                    type(payload['model']) is not HistGradientBoostingRegressor or
                    type(payload['spec']) is not FeatureSpec or type(payload['transform']) is not FeatureTransform or
                    payload['features_version'] != result['features_version'] or
                    payload['prediction_range'] != ((0, 100) if target == 'health' else (0, None)) or
                    target == 'rul' and (payload['target'] != result[target]['target'] or
                        payload['unit'] != result[target]['unit'])):
                raise ValueError('Invalid model payload contract')
            stored_spec = FeatureSpec(payload['spec'].sensors, payload['spec'].windows_seconds)
            stored_transform = FeatureTransform.from_dict(payload['transform'].to_dict())
            estimator = payload['model']
            if (stored_spec != spec or stored_transform.to_dict() != transform.to_dict() or
                    estimator.n_features_in_ != len(spec.names) or
                    estimator.get_params() != reports[target]['selection']['parameters']):
                raise ValueError('Model does not match prepared contract')
            with threadpool_limits(limits=1):
                prediction = estimator.predict(transform.apply(transform.medians[None, :], spec.names))
            if prediction.shape != (1,) or not np.isfinite(prediction).all():
                raise ValueError('Model cannot predict a finite row')
            loaded[target] = estimator
        return LoadedBundle(UUID(result['model_id']), result['model_version'], result['features_version'],
            loaded['health'], loaded['rul'], spec, transform,
            {target: result[target]['unit'] for target in ('health', 'rul')})
    except (TrainingResultUnavailable, OSError, ValueError, TypeError, KeyError, IndexError,
            OverflowError, EOFError, RecursionError, AttributeError, ImportError,
            RuntimeError, pickle.UnpicklingError) as error:
        raise ModelBundleUnavailable('Model bundle unavailable') from error
