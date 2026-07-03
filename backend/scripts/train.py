"""Train the XGBoost model on local Parquet data and save the artifact.

Chronological 70/30 split with a purge gap; prints validation metrics.
The in-sample-adjacent numbers printed here are development feedback only —
the honest evaluation is Slice 3's walk-forward.

Usage:
    uv run python scripts/train.py
    uv run python scripts/train.py --name xgb_v1 --symbol PF_XBTUSD --timeframe 1h
"""

import argparse
import math
from pathlib import Path
from typing import cast, get_args

from tradingbot.adapters.filesystem.model_store import ModelStore
from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.core.models.dataset import build_dataset
from tradingbot.core.models.train import train_model
from tradingbot.core.ports.market_data import Timeframe

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data" / "raw" / "ohlcv"
DEFAULT_MODELS_DIR = BACKEND_DIR / "data" / "models"


class _Args(argparse.Namespace):
    symbol: str
    timeframe: str
    name: str
    data_dir: Path
    models_dir: Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--timeframe", default="1h", choices=get_args(Timeframe.__value__))
    parser.add_argument("--name", default="xgb_v1")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    args = parser.parse_args(namespace=_Args())
    timeframe = cast(Timeframe, args.timeframe)  # narrowed by argparse choices

    ohlcv = ParquetStore(args.data_dir).read(args.symbol, timeframe)
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


if __name__ == "__main__":
    main()
