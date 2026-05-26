"""Fault-tolerant loader for Cricsheet JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data_quality import validate_match_record
from src.utils import configure_logging, discover_json_files

logger = configure_logging(__name__)


def validate_match_schema(record: dict[str, Any], source: Path) -> bool:
    """Validate the minimal schema required for downstream transformations."""
    is_valid, errors, _warnings = validate_match_record(record, source.name)
    if not is_valid:
        logger.warning("Skipping %s because schema validation failed: %s", source, errors)
    return is_valid


def load_match_file(path: Path) -> dict[str, Any] | None:
    """Load one Cricsheet JSON file and return None for invalid input."""
    try:
        with path.open("r", encoding="utf-8") as file:
            record = json.load(file)
    except json.JSONDecodeError as exc:
        logger.error("Malformed JSON skipped: %s | %s", path, exc)
        return None
    except OSError as exc:
        logger.error("Could not read file skipped: %s | %s", path, exc)
        return None

    if not isinstance(record, dict):
        logger.warning("Skipping %s because root JSON value is not an object", path)
        return None

    if not validate_match_schema(record, path):
        return None

    record["_source_file"] = path.name
    record["_match_id"] = path.stem
    return record


def load_matches(raw_dir: Path) -> list[dict[str, Any]]:
    """Load all valid JSON matches from a raw data directory."""
    files = discover_json_files(raw_dir)
    if not files:
        logger.warning("No JSON files found in %s", raw_dir)
        return []

    matches: list[dict[str, Any]] = []
    for path in files:
        record = load_match_file(path)
        if record is not None:
            matches.append(record)

    logger.info("Loaded %s valid matches from %s files", len(matches), len(files))
    return matches
