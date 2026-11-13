"""Opt-in checks of built images; no application services or personal volumes."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[3]
PYTHON_IMAGES = {
    "backend": ["backend.app.api.app", "backend.app.job_worker",
                "backend.app.model_worker", "backend.app.inference_worker",
                "backend.app.llm_worker"],
    "gateway": ["gateway.runtime"],
    "writer": ["writer.runtime"],
    "simulator": ["simulator.runtime"],
}
SERVICES = (*PYTHON_IMAGES, "frontend", "generation", "training", "models", "llm")


def image_contents(service, modules):
    name = "coldsafe-image-check-" + uuid4().hex
    program = """
import hashlib, importlib, json
from pathlib import Path
for module in MODULES:
    importlib.import_module(module)
files = {str(p.relative_to('/app')): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in Path('/app').rglob('*') if p.is_file()}
print(json.dumps(files))
""".replace("MODULES", repr(modules))
    try:
        result = subprocess.run(
            ["docker", "run", "--pull", "never", "--name", name, "--network", "none", "--read-only",
             "--label", "com.docker.compose.project=coldsafe-image-check",
             "--label", "com.docker.compose.service=image-check",
             "--env", "PYTHONDONTWRITEBYTECODE=1", "--entrypoint", "python",
             "coldsafe-" + service, "-c", program],
            capture_output=True, text=True, check=True, timeout=60,
        )
        return json.loads(result.stdout.splitlines()[-1])
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                       text=True, check=True, timeout=15)


@unittest.skipUnless(os.environ.get("COLDSAFE_IMAGE_TESTS") == "1",
                     "Set COLDSAFE_IMAGE_TESTS=1 after building the images")
class ApplicationImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {name: image_contents(name, modules)
                     for name, modules in PYTHON_IMAGES.items()}

    def test_runtime_modules_and_assets_match_the_checkout(self):
        expected = {
            "backend": ["backend/app/**/*.py", "backend/__init__.py",
                        "backend/migrations/*.sql", "gateway/*.py", "simulator/*.py",
                        "contracts/*.schema.json"],
            "gateway": ["gateway/*.py", "simulator/model.py", "simulator/health.py",
                        "contracts/aiot.schema.json"],
            "writer": ["backend/app/**/*.py", "writer/*.py", "gateway/bridge.py",
                       "simulator/model.py", "simulator/health.py", "contracts/aiot.schema.json"],
            "simulator": ["simulator/*.py", "contracts/aiot.schema.json"],
        }
        for service, patterns in expected.items():
            for pattern in patterns:
                paths = list(ROOT.glob(pattern))
                self.assertTrue(paths, pattern)
                for path in paths:
                    with self.subTest(service=service, path=path.relative_to(ROOT)):
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        self.assertEqual(self.files[service].get(path.relative_to(ROOT).as_posix()), digest)

    def test_production_images_exclude_tests_and_documentation(self):
        for service, files in self.files.items():
            with self.subTest(service=service):
                self.assertTrue(files)
                self.assertFalse(any("tests" in Path(p).parts or
                                     Path(p).suffix == ".md" for p in files))

    def test_application_images_identify_the_source_revision(self):
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           text=True).strip()
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=ROOT).returncode
        self.assertIn(dirty, (0, 1))
        result = subprocess.run(["docker", "image", "inspect",
                                 *("coldsafe-" + s for s in SERVICES)],
                                capture_output=True, text=True, check=True, timeout=20)
        for service, image in zip(SERVICES, json.loads(result.stdout), strict=True):
            with self.subTest(service=service):
                labels = image["Config"].get("Labels") or {}
                actual = labels.get("org.opencontainers.image.revision")
                self.assertIn(actual, (revision, revision + "-dirty"))
                if dirty:
                    self.assertEqual(actual, revision + "-dirty")
                self.assertEqual(labels.get("org.opencontainers.image.source"),
                                 "https://github.com/VitorFcosta/ColdSafe.git")


if __name__ == "__main__":
    unittest.main()
