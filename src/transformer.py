"""Transform nested Cricsheet JSON into analytical Pandas tables."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from src.cleaner import clean_deliveries, clean_matches
from src.loader import load_matches
from src.utils import PROCESSED_DATA_DIR, RAW_DATA_DIR, configure_logging

logger = configure_logging(__name__)


def _first_date(dates: Iterable[Any] | Any) -> str | None:
    if isinstance(dates, list) and dates:
        return str(dates[0])
    if dates:
        return str(dates)
    return None


def _winner(info: dict[str, Any]) -> str | None:
    outcome = info.get("outcome", {})
    if isinstance(outcome, dict):
        return outcome.get("winner")
    return None


def _event_name(info: dict[str, Any]) -> str | None:
    event = info.get("event", {})
    if isinstance(event, dict):
        return event.get("name")
    return None


def _event_stage(info: dict[str, Any]) -> str | None:
    event = info.get("event", {})
    if isinstance(event, dict):
        return event.get("stage")
    return None


def _is_pressure_match(info: dict[str, Any]) -> bool:
    event = _event_name(info) or ""
    stage = _event_stage(info) or ""
    match_type_number = str(info.get("match_type_number", "")).lower()
    labels = f"{event} {stage} {match_type_number}".lower()
    return any(token in labels for token in ("final", "qualifier", "eliminator", "playoff"))


def _extract_matches(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        info = record.get("info", {})
        rows.append(
            {
                "match_id": record.get("_match_id"),
                "source_file": record.get("_source_file"),
                "season": info.get("season"),
                "date": _first_date(info.get("dates")),
                "team_type": info.get("team_type"),
                "match_type": info.get("match_type"),
                "gender": info.get("gender"),
                "venue": info.get("venue"),
                "city": info.get("city"),
                "teams": info.get("teams", []),
                "players": info.get("players", {}),
                "toss_winner": info.get("toss", {}).get("winner")
                if isinstance(info.get("toss"), dict)
                else None,
                "toss_decision": info.get("toss", {}).get("decision")
                if isinstance(info.get("toss"), dict)
                else None,
                "winner": _winner(info),
                "event_name": _event_name(info),
                "event_stage": _event_stage(info),
                "is_pressure_match": _is_pressure_match(info),
            }
        )
    return clean_matches(pd.DataFrame(rows))


def _extract_wicket(delivery: dict[str, Any]) -> tuple[str | None, str | None, int]:
    wickets = delivery.get("wickets", [])
    if not isinstance(wickets, list) or not wickets:
        return None, None, 0
    first = wickets[0] if isinstance(wickets[0], dict) else {}
    return first.get("player_out"), first.get("kind"), 1


def _extract_deliveries(records: list[dict[str, Any]], matches: pd.DataFrame) -> pd.DataFrame:
    metadata = matches.set_index("match_id")[["season", "venue", "winner", "is_pressure_match"]]
    rows: list[dict[str, Any]] = []

    for record in records:
        match_id = record.get("_match_id")
        for innings_index, innings in enumerate(record.get("innings", []), start=1):
            if not isinstance(innings, dict):
                logger.warning("Skipping invalid innings in match %s", match_id)
                continue
            batting_team = innings.get("team")
            overs = innings.get("overs", [])
            if not isinstance(overs, list):
                logger.warning("Skipping invalid overs in match %s", match_id)
                continue

            for over_record in overs:
                if not isinstance(over_record, dict):
                    continue
                over_number = over_record.get("over")
                deliveries = over_record.get("deliveries", [])
                if not isinstance(deliveries, list):
                    continue

                legal_ball_in_over = 0
                for delivery in deliveries:
                    if not isinstance(delivery, dict):
                        continue
                    runs = delivery.get("runs", {})
                    if not isinstance(runs, dict):
                        runs = {}
                    extras_detail = delivery.get("extras", {})
                    legal_ball = not (
                        isinstance(extras_detail, dict)
                        and ("wides" in extras_detail or "noballs" in extras_detail)
                    )
                    if legal_ball:
                        legal_ball_in_over += 1

                    player_out, wicket_kind, is_wicket = _extract_wicket(delivery)
                    bowling_team = None
                    match_teams = record.get("info", {}).get("teams", [])
                    if isinstance(match_teams, list):
                        bowling_team = next((team for team in match_teams if team != batting_team), None)

                    rows.append(
                        {
                            "match_id": match_id,
                            "innings_number": innings_index,
                            "batting_team": batting_team,
                            "bowling_team": bowling_team,
                            "over": over_number,
                            "ball": legal_ball_in_over,
                            "batter": delivery.get("batter"),
                            "bowler": delivery.get("bowler"),
                            "non_striker": delivery.get("non_striker"),
                            "batter_runs": runs.get("batter", 0),
                            "extras": runs.get("extras", 0),
                            "total_runs": runs.get("total", 0),
                            "legal_ball": int(legal_ball),
                            "is_four": int(runs.get("batter", 0) == 4),
                            "is_six": int(runs.get("batter", 0) == 6),
                            "is_wicket": is_wicket,
                            "player_out": player_out,
                            "dismissed_player": player_out,
                            "wicket_kind": wicket_kind,
                        }
                    )

    deliveries = pd.DataFrame(rows)
    if deliveries.empty:
        return deliveries

    deliveries = deliveries.join(metadata, on="match_id")
    return clean_deliveries(deliveries)


def build_analytical_tables(raw_dir: Path = RAW_DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load, validate, normalize, and clean source JSON files."""
    records = load_matches(raw_dir)
    if not records:
        return pd.DataFrame(), pd.DataFrame()

    matches = _extract_matches(records)
    deliveries = _extract_deliveries(records, matches)
    logger.info("Built analytical tables: matches=%s, deliveries=%s", matches.shape, deliveries.shape)
    return matches, deliveries


def save_processed_tables(matches: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """Persist processed tables as parquet when optional engines are available."""
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        matches.to_parquet(PROCESSED_DATA_DIR / "matches.parquet", index=False)
        deliveries.to_parquet(PROCESSED_DATA_DIR / "deliveries.parquet", index=False)
    except Exception as exc:  # Parquet engines may be absent in minimal installs.
        logger.warning("Could not save parquet cache: %s", exc)
