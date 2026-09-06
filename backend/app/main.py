from backend.app.config.settings import RuntimeSettings
from backend.app.runtime import build_runtime_app


app = build_runtime_app(RuntimeSettings())
