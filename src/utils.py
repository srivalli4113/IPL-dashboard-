"""Shared utilities for the IPL analytics dashboard."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"
DATA_QUALITY_LOG_FILE = LOG_DIR / "data_quality.log"

REQUIRED_MATCH_FIELDS = ("meta", "info", "innings")
ANALYTICAL_TABLES = {
    "matches": PROCESSED_DATA_DIR / "matches.parquet",
    "deliveries": PROCESSED_DATA_DIR / "deliveries.parquet",
}


def ensure_directories() -> None:
    """Create expected project directories if they do not already exist."""
    for directory in (RAW_DATA_DIR, PROCESSED_DATA_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def configure_logging(name: str = "ipl_analytics") -> logging.Logger:
    """Configure and return a reusable project logger."""
    ensure_directories()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.WARNING)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger


def safe_divide(numerator: float, denominator: float) -> float:
    """Return a rounded ratio while avoiding divide-by-zero failures."""
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def discover_json_files(raw_dir: Path = RAW_DATA_DIR) -> list[Path]:
    """Return sorted Cricsheet JSON files from a directory."""
    if not raw_dir.exists():
        return []
    return sorted(path for path in raw_dir.glob("*.json") if path.is_file())


def comma_join(values: Iterable[object]) -> str:
    """Return a readable comma-separated string from non-empty values."""
    return ", ".join(str(value) for value in values if value is not None and value != "")
