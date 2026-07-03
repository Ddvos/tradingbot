"""Model artifact persistence: one .joblib file per named model.

Concrete class, no port yet — the in-memory fake that justifies a
ModelRegistry Protocol arrives in Slice 4 (see ADR-001).
"""

from pathlib import Path

import joblib

from tradingbot.core.models.artifact import ModelArtifact


class ModelStore:
    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def path_for(self, name: str) -> Path:
        return self._base_path / f"{name}.joblib"

    def save(self, artifact: ModelArtifact, name: str) -> Path:
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, path)
        return path

    def load(self, name: str) -> ModelArtifact:
        path = self.path_for(name)
        if not path.exists():
            raise FileNotFoundError(f"No model artifact at {path} — run scripts/train.py first")
        artifact = joblib.load(path)
        if not isinstance(artifact, ModelArtifact):
            raise TypeError(f"{path} does not contain a ModelArtifact, got {type(artifact)}")
        return artifact
