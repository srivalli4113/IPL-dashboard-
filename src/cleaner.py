"""Cleaning helpers for normalized Cricsheet tables."""

from __future__ import annotations

import pandas as pd


def clean_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Clean match-level records and normalize common data types."""
    if matches.empty:
        return matches

    cleaned = matches.copy()
    cleaned["season"] = cleaned["season"].astype("string").fillna("Unknown")
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    for column in (
        "team_type",
        "venue",
        "city",
        "toss_winner",
        "toss_decision",
        "winner",
        "event_name",
        "event_stage",
        "match_type",
        "gender",
    ):
        if column in cleaned:
            cleaned[column] = cleaned[column].astype("string").fillna("Unknown")

    cleaned["teams"] = cleaned["teams"].apply(lambda value: value if isinstance(value, list) else [])
    cleaned["players"] = cleaned["players"].apply(
        lambda value: value if isinstance(value, dict) else {}
    )
    cleaned["is_result"] = cleaned["winner"].ne("Unknown")
    return cleaned


def clean_deliveries(deliveries: pd.DataFrame) -> pd.DataFrame:
    """Clean delivery-level records, preserving rows with partial valid data."""
    if deliveries.empty:
        return deliveries

    cleaned = deliveries.copy()
    string_columns = [
        "match_id",
        "season",
        "venue",
        "batting_team",
        "bowling_team",
        "batter",
        "bowler",
        "non_striker",
        "dismissed_player",
        "wicket_kind",
        "player_out",
    ]
    for column in string_columns:
        if column in cleaned:
            cleaned[column] = cleaned[column].astype("string").fillna("Unknown")

    numeric_columns = [
        "innings_number",
        "over",
        "ball",
        "batter_runs",
        "extras",
        "total_runs",
        "is_wicket",
        "legal_ball",
        "is_four",
        "is_six",
    ]
    for column in numeric_columns:
        if column in cleaned:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce").fillna(0)

    cleaned["phase"] = pd.cut(
        cleaned["over"],
        bins=[-1, 5, 14, 19, 100],
        labels=["Powerplay", "Middle Overs", "Death Overs", "Super Over"],
    ).astype("string")
    return cleaned
