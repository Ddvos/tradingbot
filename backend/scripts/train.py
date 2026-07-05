"""Train the XGBoost model on local Parquet data and save the artifact.

Chronological 70/30 split with a purge gap; prints validation metrics.
The in-sample-adjacent numbers printed here are development feedback only —
the honest evaluation is Slice 3's walk-forward.

Usage:
    uv run python scripts/train.py
    uv run python scripts/train.py --name xgb_v1 --symbol PF_XBTUSD --timeframe 1h
    uv run python scripts/train.py --register   # also record it in the model registry
"""

import argparse
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, get_args
from uuid import uuid4

from tradingbot.adapters.filesystem.model_store import ModelStore
from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.application.holdout import clamp_to_development
from tradingbot.application.persistence import build_postgres_repositories
from tradingbot.config.settings import Settings
from tradingbot.core.models.dataset import build_dataset
from tradingbot.core.models.train import train_model
from tradingbot.core.ports.market_data import Timeframe
from tradingbot.core.ports.storage import ModelId, ModelRecord

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data" / "raw" / "ohlcv"
DEFAULT_MODELS_DIR = BACKEND_DIR / "data" / "models"


class _Args(argparse.Namespace):
    symbol: str
    timeframe: str
    name: str
    data_dir: Path
    models_dir: Path
    register: bool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--timeframe", default="1h", choices=get_args(Timeframe.__value__))
    parser.add_argument("--name", default="xgb_v1")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument(
        "--register",
        action="store_true",
        help="record the model in the Postgres registry (upserts on name)",
    )
    args = parser.parse_args(namespace=_Args())
    timeframe = cast(Timeframe, args.timeframe)  # narrowed by argparse choices

    # Development data only — training must never see the holdout (HOLDOUT.md).
    ohlcv = clamp_to_development(ParquetStore(args.data_dir).read(args.symbol, timeframe))
    dataset = build_dataset(ohlcv)
    print(
        f"Dataset: {dataset.height} rows from {ohlcv.height} bars "
        f"({dataset[0, 'timestamp']} -> {dataset[-1, 'timestamp']})"
    )

    artifact = train_model(dataset)
    m = artifact.metrics
    print(f"  Train / valid   : {m.n_train} / {m.n_valid} rows (chronological, purged)")
    print(f"  Base rate       : {m.base_rate:>8.3f}")
    print(f"  Validation AUC  : {m.auc:>8.3f}")
    sanity = "finite" if math.isfinite(m.ic) else "NOT FINITE"
    print(f"  Validation IC   : {m.ic:>8.4f}  (sanity: {sanity})")

    path = ModelStore(args.models_dir).save(artifact, args.name)
    print(f"Artifact saved to {path}")

    if args.register:
        record = ModelRecord(
            id=ModelId(uuid4()),
            name=args.name,
            artifact_path=str(path),
            auc=m.auc,
            ic=m.ic,
            trained_at=artifact.trained_at,
            created_at=datetime.now(UTC),
        )
        build_postgres_repositories(Settings().database_url).models.register(record)
        print(f"Model registered in database as {args.name}")


if __name__ == "__main__":
    main()
