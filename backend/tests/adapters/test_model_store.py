from pathlib import Path

import joblib
import pytest

from tradingbot.adapters.filesystem.model_store import ModelStore
from tradingbot.core.models.artifact import ModelArtifact


def test_save_load_roundtrip(tmp_path: Path, ml_artifact: ModelArtifact) -> None:
    store = ModelStore(tmp_path)

    store.save(ml_artifact, "test_model")
    loaded = store.load("test_model")

    assert loaded.feature_columns == ml_artifact.feature_columns
    assert loaded.trained_at == ml_artifact.trained_at
    assert loaded.metrics == ml_artifact.metrics


def test_load_missing_model_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="train"):
        ModelStore(tmp_path).load("nope")


def test_load_rejects_foreign_content(tmp_path: Path) -> None:
    store = ModelStore(tmp_path)
    joblib.dump({"not": "an artifact"}, store.path_for("bad"))

    with pytest.raises(TypeError, match="ModelArtifact"):
        store.load("bad")
