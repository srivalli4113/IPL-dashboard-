"""Data quality validation and reporting for Cricsheet IPL JSON files."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import DATA_QUALITY_LOG_FILE, RAW_DATA_DIR, REQUIRED_MATCH_FIELDS, discover_json_files, ensure_directories

MATCH_INFO_REQUIRED = ("dates", "teams", "venue", "event", "match_type", "gender")
TOSS_REQUIRED = ("winner", "decision")


def quality_logger() -> logging.Logger:
    """Return a logger dedicated to data-quality events."""
    ensure_directories()
    logger = logging.getLogger("ipl_analytics.data_quality")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler = logging.FileHandler(DATA_QUALITY_LOG_FILE, encoding="utf-8")
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
    return logger


@dataclass(frozen=True)
class DataQualityReport:
    """Summary counters produced by the data-quality pipeline."""

    total_files_processed: int = 0
    valid_files: int = 0
    invalid_files: int = 0
    records_skipped: int = 0
    schema_violations: int = 0
    missing_fields: int = 0
    duplicate_files: int = 0
    null_value_warnings: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_files_processed == 0:
            return 0.0
        return round(self.valid_files / self.total_files_processed * 100, 2)

    @property
    def quality_percentage(self) -> float:
        """Return valid records divided by total records as a percentage."""
        return self.success_rate

    @property
    def quality_status(self) -> str:
        """Classify the quality percentage for dashboard display."""
        if self.quality_percentage >= 95:
            return "Excellent"
        if self.quality_percentage >= 85:
            return "Good"
        return "Needs Review"

    def to_frame(self) -> pd.DataFrame:
        values = asdict(self)
        values["success_rate"] = self.success_rate
        values["quality_percentage"] = self.quality_percentage
        values["quality_status"] = self.quality_status
        return pd.DataFrame(
            [
                {"metric": "Total files processed", "value": values["total_files_processed"]},
                {"metric": "Valid files", "value": values["valid_files"]},
                {"metric": "Files rejected", "value": values["invalid_files"]},
                {"metric": "Records skipped", "value": values["records_skipped"]},
                {"metric": "Schema violations", "value": values["schema_violations"]},
                {"metric": "Missing fields", "value": values["missing_fields"]},
                {"metric": "Duplicates removed", "value": values["duplicate_files"]},
                {"metric": "Null value warnings", "value": values["null_value_warnings"]},
                {"metric": "Success rate", "value": f'{values["success_rate"]:.2f}%'},
                {"metric": "Data Quality Percentage", "value": f'{values["quality_percentage"]:.2f}%'},
                {"metric": "Quality Status", "value": values["quality_status"]},
            ]
        )


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_match_record(record: dict[str, Any], source: Path | str) -> tuple[bool, list[str], list[str]]:
    """Validate one raw match object and return validity, errors, and warnings."""
    source_name = str(source)
    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_MATCH_FIELDS:
        if field not in record:
            errors.append(f"missing top-level field: {field}")

    info = record.get("info")
    innings = record.get("innings")
    if not isinstance(info, dict):
        errors.append("info must be an object")
        info = {}
    if not isinstance(innings, list):
        errors.append("innings must be a list")
        innings = []

    for field in MATCH_INFO_REQUIRED:
        if field not in info:
            warnings.append(f"missing info field: {field}")

    teams = info.get("teams")
    if not isinstance(teams, list) or len(teams) < 2:
        errors.append("info.teams must contain at least two teams")

    venue = info.get("venue")
    if not _is_non_empty_string(venue):
        warnings.append("missing or blank venue")

    players = info.get("players")
    if not isinstance(players, dict) or not players:
        warnings.append("missing players map")
    elif isinstance(teams, list):
        for team in teams:
            if not players.get(team):
                warnings.append(f"missing player list for team: {team}")

    toss = info.get("toss")
    if not isinstance(toss, dict):
        warnings.append("missing toss data")
    else:
        for field in TOSS_REQUIRED:
            if not toss.get(field):
                warnings.append(f"missing toss field: {field}")

    if not innings:
        errors.append("innings list is empty")
    for innings_index, innings_record in enumerate(innings, start=1):
        if not isinstance(innings_record, dict):
            errors.append(f"innings[{innings_index}] must be an object")
            continue
        if not innings_record.get("team"):
            warnings.append(f"innings[{innings_index}] missing batting team")
        overs = innings_record.get("overs")
        if not isinstance(overs, list):
            errors.append(f"innings[{innings_index}].overs must be a list")

    for issue in errors:
        quality_logger().error("%s | schema violation | %s", source_name, issue)
    for issue in warnings:
        quality_logger().warning("%s | data warning | %s", source_name, issue)

    return not errors, errors, warnings


def run_data_quality_pipeline(raw_dir: Path = RAW_DATA_DIR) -> DataQualityReport:
    """Validate every JSON file, log failures, and return aggregate quality metrics."""
    log = quality_logger()
    files = discover_json_files(raw_dir)
    seen_match_ids: set[str] = set()

    valid = invalid = skipped = schema_violations = missing_fields = duplicates = warnings = 0
    log.info("Starting data-quality validation for %s files in %s", len(files), raw_dir)

    for path in files:
        match_id = path.stem
        if match_id in seen_match_ids:
            duplicates += 1
            warnings += 1
            log.warning("%s | duplicate match id detected: %s", path.name, match_id)
        seen_match_ids.add(match_id)

        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            invalid += 1
            skipped += 1
            schema_violations += 1
            log.error("%s | malformed json | %s", path.name, exc)
            continue
        except OSError as exc:
            invalid += 1
            skipped += 1
            log.error("%s | unreadable file | %s", path.name, exc)
            continue

        if not isinstance(record, dict):
            invalid += 1
            skipped += 1
            schema_violations += 1
            log.error("%s | root JSON is not an object", path.name)
            continue

        is_valid, errors, record_warnings = validate_match_record(record, path.name)
        schema_violations += len(errors)
        missing_fields += sum(1 for issue in errors + record_warnings if issue.startswith("missing"))
        warnings += len(record_warnings)
        if is_valid:
            valid += 1
        else:
            invalid += 1
            skipped += 1

    report = DataQualityReport(
        total_files_processed=len(files),
        valid_files=valid,
        invalid_files=invalid,
        records_skipped=skipped,
        schema_violations=schema_violations,
        missing_fields=missing_fields,
        duplicate_files=duplicates,
        null_value_warnings=warnings,
    )
    log.info(
        "Completed data-quality validation | total=%s valid=%s invalid=%s skipped=%s success_rate=%.2f",
        report.total_files_processed,
        report.valid_files,
        report.invalid_files,
        report.records_skipped,
        report.success_rate,
    )
    return report
