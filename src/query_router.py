"""Rule-based natural-language query router for grounded IPL analytics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable

import pandas as pd

from src.analytics import (
    batting_leaderboard,
    match_innings_roles,
    phase_batting_leaderboard,
    phase_bowling_leaderboard,
    player_impact_scores,
    season_win_rates,
    team_advanced_insights,
    venue_advanced_insights,
)

INSUFFICIENT_ANSWER = "This question cannot be answered from the available IPL dataset."


@dataclass(frozen=True)
class QueryResult:
    """Structured, explainable response returned by the query router."""

    intent: str
    answer: str
    data: pd.DataFrame
    applied_filters: dict[str, object]
    metrics_used: list[str]
    records_analysed: int
    execution_method: str
    verification_badge: str

    @property
    def source(self) -> str:
        return "Cricsheet Dataset"

    @property
    def validation(self) -> str:
        if self.verification_badge == "Verified Dataset Result":
            return "Dataset Grounded"
        return self.verification_badge


def _result(
    intent: str,
    answer: str,
    data: pd.DataFrame,
    filters: dict[str, object],
    metrics: list[str],
    records: int,
    badge: str = "Verified Dataset Result",
) -> QueryResult:
    clean_filters = {key: value for key, value in filters.items() if value not in (None, [], "", "All")}
    return QueryResult(
        intent=intent,
        answer=answer,
        data=data,
        applied_filters=clean_filters,
        metrics_used=metrics,
        records_analysed=int(records),
        execution_method="Rule-based intent detection -> deterministic Pandas analytics -> formatted response",
        verification_badge=badge,
    )


def _find_known_value(query: str, values: list[str]) -> str | None:
    query_lower = query.lower()
    for value in sorted([value for value in values if isinstance(value, str)], key=len, reverse=True):
        if value.lower() in query_lower:
            return value
    return None


def _team_list(values: object) -> list[str]:
    if isinstance(values, str) or values is None:
        return []
    if isinstance(values, Iterable):
        return [str(value) for value in values if value is not None]
    return []


def _season_filter(query: str) -> int | None:
    match = re.search(r"(?:after|since|from)\s+(20\d{2})", query.lower())
    return int(match.group(1)) if match else None


def detect_intent(query: str) -> str:
    """Classify a natural-language IPL query into a supported analytics intent."""
    q = query.lower()
    if any(token in q for token in ("death over bowler", "death bowler", "best death over bowler")):
        return "bowling_trends"
    if "impact" in q or "valuable" in q:
        return "player_impact"
    if "strike rate" in q or "1000+ runs" in q or "1000 runs" in q:
        return "player_stats"
    if "compare" in q or " vs " in q or "versus" in q:
        return "team_comparison"
    if "venue" in q or "wankhede" in q or "dominates at" in q or " at " in q or "favors chasing" in q:
        return "venue_comparison"
    if "toss" in q:
        return "toss_analysis"
    if "season" in q or "after" in q or "since" in q:
        return "season_trends"
    if "batter" in q or "batsman" in q or "runs" in q:
        return "batting_trends"
    if "bowler" in q or "wicket" in q:
        return "bowling_trends"
    return "general"


def generate_filters(query: str, matches: pd.DataFrame, deliveries: pd.DataFrame) -> dict[str, object]:
    """Extract teams, venues, players, and seasons directly from known data values."""
    teams = sorted({team for values in matches.get("teams", []) for team in _team_list(values)})
    aliases = {
        "csk": "Chennai Super Kings",
        "mi": "Mumbai Indians",
        "rcb": "Royal Challengers Bangalore",
        "kkr": "Kolkata Knight Riders",
        "srh": "Sunrisers Hyderabad",
        "dc": "Delhi Capitals",
    }
    query_lower = query.lower()
    mentioned_teams = [team for team in teams if team.lower() in query_lower]
    for alias, team in aliases.items():
        if alias in query_lower and team in teams and team not in mentioned_teams:
            mentioned_teams.append(team)

    venues = sorted(matches["venue"].dropna().astype(str).unique().tolist()) if "venue" in matches else []
    players = sorted(set(deliveries["batter"].dropna().astype(str)).union(set(deliveries["bowler"].dropna().astype(str)))) if not deliveries.empty else []
    return {
        "team": mentioned_teams[0] if mentioned_teams else None,
        "teams": mentioned_teams[:2],
        "venue": _find_known_value(query, venues),
        "player": _find_known_value(query, players),
        "season_from": _season_filter(query),
    }


def _filter_after(matches: pd.DataFrame, deliveries: pd.DataFrame, season_from: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not season_from:
        return matches, deliveries
    match_year = pd.to_numeric(matches["season"].astype(str).str.extract(r"(\d{4})", expand=False), errors="coerce")
    delivery_year = pd.to_numeric(deliveries["season"].astype(str).str.extract(r"(\d{4})", expand=False), errors="coerce")
    match_mask = match_year.ge(season_from)
    delivery_mask = delivery_year.ge(season_from)
    return matches[match_mask], deliveries[delivery_mask]


def execute_analytics(intent: str, filters: dict[str, object], matches: pd.DataFrame, deliveries: pd.DataFrame) -> QueryResult:
    """Execute the selected analytics function and format a grounded answer."""
    matches, deliveries = _filter_after(matches, deliveries, filters.get("season_from"))

    if intent == "bowling_trends":
        table = phase_bowling_leaderboard(deliveries, "Death Overs", min_overs=8).head(10)
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Bowling Impact Score"], 0, "Insufficient Data")
        row = table.iloc[0]
        return _result(intent, f"{row['bowler']} is the best death-over bowler by the current impact model: {int(row['wickets'])} wickets, economy {row['economy']:.2f}.", table, filters, ["Bowling Impact Score", "Wickets", "Economy"], len(table))

    if intent == "player_stats":
        table = batting_leaderboard(deliveries, min_balls=1)
        table = table[table["runs"] >= 1000].sort_values("strike_rate", ascending=False).head(10)
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Runs", "Strike Rate"], 0, "Insufficient Data")
        row = table.iloc[0]
        return _result(intent, f"{row['batter']} has the highest strike rate among 1000+ run players: {row['strike_rate']:.2f} with {int(row['runs'])} runs.", table, filters, ["Runs", "Strike Rate"], len(table))

    if intent == "player_impact":
        table = player_impact_scores(deliveries, min_balls=60).head(10)
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Player Impact Score"], 0, "Insufficient Data")
        row = table.iloc[0]
        return _result(intent, f"{row['batter']} is the most impactful batter in this selection with an impact score of {row['impact_score']:.2f}.", table, filters, ["Player Impact Score", "Runs", "Strike Rate", "Boundary %", "Match-Winning Contribution"], len(table))

    if intent == "team_comparison":
        teams = filters.get("teams") or []
        if len(teams) < 2:
            return _result(intent, INSUFFICIENT_ANSWER, pd.DataFrame(), filters, ["Win Rate"], 0, "Insufficient Data")
        table = team_advanced_insights(matches, deliveries)
        table = table[table["team"].isin(teams)]
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Win Rate"], 0, "Insufficient Data")
        leader = table.sort_values("win_pct", ascending=False).iloc[0]
        return _result(intent, f"{leader['team']} leads this comparison with a {leader['win_pct']:.2f}% win rate and {leader['chasing_strength_score']:.2f} chasing strength score.", table, filters, ["Win Rate", "Chasing Efficiency", "Defending Efficiency"], len(table))

    if intent == "venue_comparison":
        venue = filters.get("venue")
        roles = match_innings_roles(matches, deliveries)
        if venue:
            venue_roles = roles[roles["venue"].eq(venue)]
            if venue_roles.empty:
                return _result(intent, INSUFFICIENT_ANSWER, venue_roles, filters, ["Venue Win Rate"], 0, "Insufficient Data")
            team_rows = []
            for team in sorted({team for values in venue_roles["teams"] for team in _team_list(values)}):
                played = venue_roles["teams"].apply(lambda values: team in _team_list(values))
                wins = venue_roles["winner"].eq(team)
                team_rows.append({"team": team, "matches": int(played.sum()), "wins": int((played & wins).sum())})
            table = pd.DataFrame(team_rows)
            table["win_pct"] = (table["wins"] / table["matches"] * 100).fillna(0).round(2)
            table = table.sort_values(["wins", "win_pct"], ascending=False)
            row = table.iloc[0]
            return _result(intent, f"{row['team']} dominates at {venue} with {int(row['wins'])} wins from {int(row['matches'])} matches.", table, filters, ["Venue Win Rate", "Wins"], len(venue_roles))
        table = venue_advanced_insights(matches, deliveries).head(10)
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Venue Bias Index"], 0, "Insufficient Data")
        row = table.sort_values("chasing_success_pct", ascending=False).iloc[0]
        return _result(intent, f"{row['venue']} has the strongest chasing signal in this selection at {row['chasing_success_pct']:.2f}%.", table, filters, ["Venue Bias Index", "Chasing Success %"], len(table))

    if intent == "toss_analysis":
        roles = match_innings_roles(matches, deliveries)
        if roles.empty:
            return _result(intent, INSUFFICIENT_ANSWER, roles, filters, ["Toss Winner Match Win %"], 0, "Insufficient Data")
        rate = roles["toss_winner_won"].mean() * 100
        table = roles.groupby("toss_decision", as_index=False).agg(matches=("match_id", "count"), toss_winner_win_pct=("toss_winner_won", lambda s: round(s.mean() * 100, 2)))
        return _result(intent, f"Winning the toss leads to a match win {rate:.2f}% of the time in the selected data.", table, filters, ["Toss Winner Match Win %"], len(roles))

    if intent == "season_trends":
        table = season_win_rates(matches).head(25)
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Season Win Rate"], 0, "Insufficient Data")
        row = table.sort_values("win_pct", ascending=False).iloc[0]
        return _result(intent, f"{row['team']} owns the strongest season result in this selection: {row['win_pct']:.2f}% in {row['season']}.", table, filters, ["Season Win Rate"], len(table))

    if intent == "batting_trends":
        table = phase_batting_leaderboard(deliveries, "Powerplay", min_balls=60).head(10)
        if table.empty:
            return _result(intent, INSUFFICIENT_ANSWER, table, filters, ["Powerplay Runs", "Strike Rate"], 0, "Insufficient Data")
        row = table.iloc[0]
        return _result(intent, f"{row['batter']} leads powerplay batting by runs in the selected data: {int(row['runs'])} runs at SR {row['strike_rate']:.2f}.", table, filters, ["Powerplay Runs", "Strike Rate"], len(table))

    return _result("general", INSUFFICIENT_ANSWER, pd.DataFrame(), filters, [], 0, "Insufficient Data")


def route_query(query: str, matches: pd.DataFrame, deliveries: pd.DataFrame) -> QueryResult:
    """Route a natural-language query to deterministic, dataset-grounded analytics."""
    intent = detect_intent(query)
    filters = generate_filters(query, matches, deliveries)
    return execute_analytics(intent, filters, matches, deliveries)
