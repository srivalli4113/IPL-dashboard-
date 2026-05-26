"""Reusable analytics engine for IPL-style Cricsheet data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils import safe_divide

NON_BOWLER_WICKET_KINDS = {
    "run out",
    "retired hurt",
    "retired out",
    "obstructing the field",
}


def overview_metrics(matches: pd.DataFrame, deliveries: pd.DataFrame) -> dict[str, int]:
    """Return top-level dashboard metrics."""
    players: set[str] = set()
    if not matches.empty and "players" in matches:
        for player_map in matches["players"]:
            if isinstance(player_map, dict):
                for names in player_map.values():
                    if isinstance(names, list):
                        players.update(str(name) for name in names)

    return {
        "matches": int(matches["match_id"].nunique()) if not matches.empty else 0,
        "seasons": int(matches["season"].nunique()) if not matches.empty else 0,
        "venues": int(matches["venue"].nunique()) if not matches.empty else 0,
        "players": int(len(players) or deliveries[["batter", "bowler"]].stack().nunique())
        if not deliveries.empty
        else 0,
        "runs": int(deliveries["total_runs"].sum()) if not deliveries.empty else 0,
        "wickets": int(deliveries["is_wicket"].sum()) if not deliveries.empty else 0,
    }


def explode_team_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Create one row per team per match with result flags."""
    if matches.empty:
        return pd.DataFrame()
    exploded = matches[["match_id", "season", "venue", "teams", "winner"]].explode("teams")
    exploded = exploded.rename(columns={"teams": "team"})
    exploded = exploded[exploded["team"].notna()]
    exploded["played"] = 1
    exploded["wins"] = (exploded["team"] == exploded["winner"]).astype(int)
    exploded["losses"] = ((exploded["winner"] != "Unknown") & (exploded["team"] != exploded["winner"])).astype(int)
    return exploded


def team_win_rates(matches: pd.DataFrame) -> pd.DataFrame:
    """Return overall team win percentage."""
    team_matches = explode_team_matches(matches)
    if team_matches.empty:
        return team_matches
    grouped = team_matches.groupby("team", as_index=False).agg(matches=("played", "sum"), wins=("wins", "sum"))
    grouped["win_pct"] = (grouped["wins"] / grouped["matches"] * 100).round(2)
    return grouped.sort_values(["win_pct", "wins"], ascending=False)


def season_win_rates(matches: pd.DataFrame) -> pd.DataFrame:
    """Return team win percentage by season."""
    team_matches = explode_team_matches(matches)
    if team_matches.empty:
        return team_matches
    grouped = team_matches.groupby(["season", "team"], as_index=False).agg(matches=("played", "sum"), wins=("wins", "sum"))
    grouped["win_pct"] = (grouped["wins"] / grouped["matches"] * 100).round(2)
    return grouped.sort_values(["season", "win_pct"], ascending=[True, False])


def batting_leaderboard(deliveries: pd.DataFrame, min_balls: int = 30) -> pd.DataFrame:
    """Compute batting runs, strike rate, boundaries, and consistency index."""
    if deliveries.empty:
        return pd.DataFrame()

    batting = deliveries.groupby("batter", as_index=False).agg(
        runs=("batter_runs", "sum"),
        balls=("legal_ball", "sum"),
        fours=("is_four", "sum"),
        sixes=("is_six", "sum"),
        innings=("match_id", "nunique"),
    )
    dismissals = (
        deliveries[
            deliveries["dismissed_player"].notna()
            & deliveries["dismissed_player"].ne("Unknown")
            & deliveries["wicket_kind"].str.lower().ne("retired hurt")
        ]
        .groupby("dismissed_player", as_index=False)
        .agg(dismissals=("match_id", "count"))
        .rename(columns={"dismissed_player": "batter"})
    )
    per_match = deliveries.groupby(["batter", "match_id"], as_index=False).agg(match_runs=("batter_runs", "sum"))
    consistency = (
        per_match.groupby("batter", as_index=False)
        .agg(avg_runs=("match_runs", "mean"), run_std=("match_runs", "std"), fifties=("match_runs", lambda s: int((s >= 50).sum())))
        .fillna({"run_std": 0})
    )
    batting = batting.merge(consistency, on="batter", how="left").merge(dismissals, on="batter", how="left")
    batting["dismissals"] = batting["dismissals"].fillna(0).astype(int)
    batting["strike_rate"] = np.where(batting["balls"] > 0, batting["runs"] / batting["balls"] * 100, 0).round(2)
    batting["batting_average"] = np.where(batting["dismissals"] > 0, batting["runs"] / batting["dismissals"], np.nan).round(2)
    batting["boundary_runs"] = batting["fours"] * 4 + batting["sixes"] * 6
    batting["boundary_pct"] = np.where(batting["runs"] > 0, batting["boundary_runs"] / batting["runs"] * 100, 0).round(2)
    batting["consistency_index"] = np.where(
        batting["avg_runs"] > 0,
        (batting["avg_runs"] / (batting["run_std"] + 1) * np.log1p(batting["innings"])).round(2),
        0,
    )
    batting = batting[batting["balls"] >= min_balls]
    return batting.sort_values(["runs", "strike_rate"], ascending=False)


def bowling_leaderboard(deliveries: pd.DataFrame, min_overs: float = 5.0) -> pd.DataFrame:
    """Compute bowling wickets, economy, and average."""
    if deliveries.empty:
        return pd.DataFrame()

    legal = deliveries.copy()
    legal["bowler_wicket"] = (
        (legal["is_wicket"] == 1) & (~legal["wicket_kind"].str.lower().isin(NON_BOWLER_WICKET_KINDS))
    ).astype(int)
    grouped = legal.groupby("bowler", as_index=False).agg(
        balls=("legal_ball", "sum"),
        runs_conceded=("total_runs", "sum"),
        wickets=("bowler_wicket", "sum"),
        innings=("match_id", "nunique"),
    )
    grouped["overs"] = (grouped["balls"] / 6).round(1)
    grouped["economy"] = np.where(grouped["balls"] > 0, grouped["runs_conceded"] / grouped["balls"] * 6, 0).round(2)
    grouped["bowling_average"] = np.where(grouped["wickets"] > 0, grouped["runs_conceded"] / grouped["wickets"], np.nan).round(2)
    grouped = grouped[grouped["overs"] >= min_overs]
    return grouped.sort_values(["wickets", "economy"], ascending=[False, True])


def toss_impact(matches: pd.DataFrame) -> pd.DataFrame:
    """Analyze whether toss winners also won matches."""
    if matches.empty:
        return pd.DataFrame()
    valid = matches[(matches["toss_winner"] != "Unknown") & (matches["winner"] != "Unknown")].copy()
    if valid.empty:
        return valid
    valid["toss_winner_won"] = valid["toss_winner"] == valid["winner"]
    grouped = valid.groupby("toss_decision", as_index=False).agg(
        matches=("match_id", "count"),
        toss_winner_wins=("toss_winner_won", "sum"),
    )
    grouped["toss_win_match_win_pct"] = (grouped["toss_winner_wins"] / grouped["matches"] * 100).round(2)
    return grouped.sort_values("matches", ascending=False)


def chase_vs_defend(matches: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Compute defending and chasing win split from innings order."""
    if matches.empty or deliveries.empty:
        return pd.DataFrame()
    innings_teams = deliveries.groupby(["match_id", "innings_number"], as_index=False).agg(team=("batting_team", "first"))
    first_bat = innings_teams[innings_teams["innings_number"] == 1][["match_id", "team"]].rename(columns={"team": "batting_first"})
    second_bat = innings_teams[innings_teams["innings_number"] == 2][["match_id", "team"]].rename(columns={"team": "chasing"})
    outcomes = matches[["match_id", "winner", "venue"]].merge(first_bat, on="match_id", how="left").merge(second_bat, on="match_id", how="left")
    outcomes = outcomes[outcomes["winner"] != "Unknown"].copy()
    chasing_win = outcomes["winner"].eq(outcomes["chasing"]).fillna(False)
    outcomes["result_type"] = np.where(chasing_win, "Chasing", "Defending")
    return outcomes.groupby("result_type", as_index=False).agg(matches=("match_id", "count")).sort_values("matches", ascending=False)


def venue_trends(matches: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Return venue scoring and chase outcome metrics."""
    if matches.empty or deliveries.empty:
        return pd.DataFrame()

    innings_scores = deliveries.groupby(["match_id", "venue", "innings_number"], as_index=False).agg(runs=("total_runs", "sum"))
    first_scores = innings_scores[innings_scores["innings_number"] == 1].rename(columns={"runs": "first_innings_score"})
    second_scores = innings_scores[innings_scores["innings_number"] == 2].rename(columns={"runs": "second_innings_score"})
    combined = first_scores[["match_id", "venue", "first_innings_score"]].merge(
        second_scores[["match_id", "second_innings_score"]], on="match_id", how="left"
    )
    chase = chase_vs_defend(matches, deliveries)
    outcomes = matches[["match_id", "winner"]].merge(combined, on="match_id", how="inner")

    innings_teams = deliveries.groupby(["match_id", "innings_number"], as_index=False).agg(team=("batting_team", "first"))
    chasing = innings_teams[innings_teams["innings_number"] == 2][["match_id", "team"]].rename(columns={"team": "chasing"})
    outcomes = outcomes.merge(chasing, on="match_id", how="left")
    outcomes["chase_success"] = outcomes["winner"].eq(outcomes["chasing"]).fillna(False)
    outcomes["successful_chase_score"] = np.where(
        outcomes["chase_success"].astype(bool),
        outcomes["second_innings_score"],
        np.nan,
    )

    grouped = outcomes.groupby("venue", as_index=False).agg(
        matches=("match_id", "nunique"),
        avg_first_innings_score=("first_innings_score", "mean"),
        chase_success_rate=("chase_success", "mean"),
        highest_successful_chase=("successful_chase_score", "max"),
    )
    grouped["avg_first_innings_score"] = grouped["avg_first_innings_score"].round(2)
    grouped["chase_success_rate"] = (grouped["chase_success_rate"] * 100).round(2)
    grouped["highest_successful_chase"] = grouped["highest_successful_chase"].fillna(0).astype(int)
    return grouped.sort_values("matches", ascending=False)


def phase_scoring(deliveries: pd.DataFrame) -> pd.DataFrame:
    """Return scoring rates by innings phase."""
    if deliveries.empty:
        return pd.DataFrame()
    grouped = deliveries.groupby(["season", "phase"], as_index=False).agg(
        runs=("total_runs", "sum"),
        balls=("legal_ball", "sum"),
    )
    grouped["run_rate"] = np.where(grouped["balls"] > 0, grouped["runs"] / grouped["balls"] * 6, 0).round(2)
    return grouped


def team_momentum(matches: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Compute rolling team win percentage across chronological matches."""
    team_matches = explode_team_matches(matches)
    if team_matches.empty:
        return team_matches
    ordered = team_matches.merge(matches[["match_id", "date"]], on="match_id", how="left").sort_values(["team", "date"])
    ordered["rolling_win_pct"] = (
        ordered.groupby("team")["wins"]
        .rolling(window=window, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
        .mul(100)
        .round(2)
    )
    return ordered


def pressure_match_summary(matches: pd.DataFrame) -> pd.DataFrame:
    """Summarize team performance in playoff/final-style matches when labels exist."""
    if matches.empty or "is_pressure_match" not in matches:
        return pd.DataFrame()
    pressure = matches[matches["is_pressure_match"]].copy()
    return team_win_rates(pressure) if not pressure.empty else pd.DataFrame()


def team_peak_snapshot(matches: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Return one peak-performance summary row per team.

    The snapshot combines team peak season, team run rate, leading batter,
    leading bowler, and best scoring phase. All values are computed from the
    loaded dataset and are intentionally not hardcoded.
    """
    if matches.empty or deliveries.empty:
        return pd.DataFrame()

    season_performance = season_win_rates(matches)
    if season_performance.empty:
        return pd.DataFrame()

    team_season_runs = (
        deliveries.groupby(["season", "batting_team"], as_index=False)
        .agg(team_runs=("total_runs", "sum"), team_balls=("legal_ball", "sum"))
        .rename(columns={"batting_team": "team"})
    )
    team_season_runs["team_run_rate"] = np.where(
        team_season_runs["team_balls"] > 0,
        team_season_runs["team_runs"] / team_season_runs["team_balls"] * 6,
        0,
    ).round(2)

    peak_season = season_performance.merge(team_season_runs, on=["season", "team"], how="left")
    peak_season = peak_season.sort_values(
        ["team", "win_pct", "team_run_rate", "wins"],
        ascending=[True, False, False, False],
    ).drop_duplicates("team", keep="first")
    peak_season = peak_season.rename(
        columns={
            "season": "peak_season",
            "matches": "peak_matches",
            "wins": "peak_wins",
            "win_pct": "peak_win_pct",
        }
    )

    batting = deliveries.groupby(["batting_team", "batter"], as_index=False).agg(
        batter_runs=("batter_runs", "sum"),
        batter_balls=("legal_ball", "sum"),
        batter_fours=("is_four", "sum"),
        batter_sixes=("is_six", "sum"),
    )
    batting = batting.rename(columns={"batting_team": "team", "batter": "peak_batter"})
    batting["batter_strike_rate"] = np.where(
        batting["batter_balls"] > 0,
        batting["batter_runs"] / batting["batter_balls"] * 100,
        0,
    ).round(2)
    top_batter = batting.sort_values(
        ["team", "batter_runs", "batter_strike_rate"],
        ascending=[True, False, False],
    ).drop_duplicates("team", keep="first")

    batter_seasons = deliveries.groupby(["batting_team", "batter", "season"], as_index=False).agg(
        batter_peak_runs=("batter_runs", "sum"),
        batter_peak_balls=("legal_ball", "sum"),
    )
    batter_seasons["batter_peak_strike_rate"] = np.where(
        batter_seasons["batter_peak_balls"] > 0,
        batter_seasons["batter_peak_runs"] / batter_seasons["batter_peak_balls"] * 100,
        0,
    ).round(2)
    batter_seasons = batter_seasons.rename(
        columns={"batting_team": "team", "batter": "peak_batter", "season": "batter_peak_season"}
    )
    batter_peak = batter_seasons.sort_values(
        ["team", "peak_batter", "batter_peak_runs", "batter_peak_strike_rate"],
        ascending=[True, True, False, False],
    ).drop_duplicates(["team", "peak_batter"], keep="first")
    top_batter = top_batter.merge(
        batter_peak[
            [
                "team",
                "peak_batter",
                "batter_peak_season",
                "batter_peak_runs",
                "batter_peak_strike_rate",
            ]
        ],
        on=["team", "peak_batter"],
        how="left",
    )

    bowling = deliveries.copy()
    bowling["bowler_wicket"] = (
        (bowling["is_wicket"] == 1)
        & (~bowling["wicket_kind"].str.lower().isin(NON_BOWLER_WICKET_KINDS))
    ).astype(int)
    top_bowler = bowling.groupby(["bowling_team", "bowler"], as_index=False).agg(
        bowler_wickets=("bowler_wicket", "sum"),
        bowler_runs_conceded=("total_runs", "sum"),
        bowler_balls=("legal_ball", "sum"),
    )
    top_bowler = top_bowler.rename(columns={"bowling_team": "team", "bowler": "peak_bowler"})
    top_bowler["bowler_economy"] = np.where(
        top_bowler["bowler_balls"] > 0,
        top_bowler["bowler_runs_conceded"] / top_bowler["bowler_balls"] * 6,
        0,
    ).round(2)
    top_bowler = top_bowler.sort_values(
        ["team", "bowler_wickets", "bowler_economy"],
        ascending=[True, False, True],
    ).drop_duplicates("team", keep="first")

    phase = deliveries.groupby(["batting_team", "phase"], as_index=False).agg(
        phase_runs=("total_runs", "sum"),
        phase_balls=("legal_ball", "sum"),
    )
    phase = phase.rename(columns={"batting_team": "team", "phase": "strongest_phase"})
    phase["phase_run_rate"] = np.where(
        phase["phase_balls"] > 0,
        phase["phase_runs"] / phase["phase_balls"] * 6,
        0,
    ).round(2)
    phase = phase[phase["phase_balls"] >= 30]
    strongest_phase = phase.sort_values(
        ["team", "phase_run_rate", "phase_runs"],
        ascending=[True, False, False],
    ).drop_duplicates("team", keep="first")

    snapshot = (
        peak_season.merge(top_batter, on="team", how="left")
        .merge(top_bowler, on="team", how="left")
        .merge(strongest_phase, on="team", how="left")
    )
    return snapshot.sort_values(["peak_win_pct", "team_run_rate"], ascending=False)


def filter_by_season(df: pd.DataFrame, seasons: list[str] | None) -> pd.DataFrame:
    """Filter any table containing a season column."""
    if df.empty or not seasons or "All" in seasons or "season" not in df:
        return df
    return df[df["season"].astype(str).isin([str(season) for season in seasons])]


def filter_by_team_matches(matches: pd.DataFrame, teams: list[str] | None) -> pd.DataFrame:
    """Filter matches involving selected teams."""
    if matches.empty or not teams or "All" in teams:
        return matches
    return matches[matches["teams"].apply(lambda values: bool(set(values).intersection(teams)) if isinstance(values, list) else False)]


def match_innings_roles(matches: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Return match outcomes enriched with first-batting and chasing teams."""
    if matches.empty or deliveries.empty:
        return pd.DataFrame()
    innings_teams = deliveries.groupby(["match_id", "innings_number"], as_index=False).agg(team=("batting_team", "first"))
    first = innings_teams[innings_teams["innings_number"] == 1][["match_id", "team"]].rename(columns={"team": "batting_first"})
    second = innings_teams[innings_teams["innings_number"] == 2][["match_id", "team"]].rename(columns={"team": "chasing_team"})
    roles = matches[["match_id", "season", "date", "venue", "teams", "winner", "toss_winner", "toss_decision"]].merge(first, on="match_id", how="left").merge(second, on="match_id", how="left")
    roles = roles[roles["winner"].notna() & roles["winner"].ne("Unknown")].copy()
    roles["chasing_win"] = roles["winner"].eq(roles["chasing_team"]).fillna(False)
    roles["defending_win"] = roles["winner"].eq(roles["batting_first"]).fillna(False)
    roles["toss_winner_won"] = roles["winner"].eq(roles["toss_winner"]).fillna(False)
    return roles


def team_advanced_insights(matches: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Compute advanced team metrics for evaluation-ready team analytics."""
    if matches.empty or deliveries.empty:
        return pd.DataFrame()

    team_matches = explode_team_matches(matches)
    roles = match_innings_roles(matches, deliveries)
    if team_matches.empty or roles.empty:
        return pd.DataFrame()

    base = team_win_rates(matches)

    venue_counts = team_matches.groupby(["team", "venue"], as_index=False).agg(venue_matches=("match_id", "nunique"))
    primary_venues = venue_counts.sort_values(["team", "venue_matches"], ascending=[True, False]).drop_duplicates("team")
    home = team_matches.merge(primary_venues[["team", "venue"]], on=["team", "venue"], how="inner")
    home_summary = home.groupby("team", as_index=False).agg(home_matches=("played", "sum"), home_wins=("wins", "sum"))
    home_summary["home_advantage_score"] = np.where(
        home_summary["home_matches"] > 0,
        home_summary["home_wins"] / home_summary["home_matches"] * 100,
        0,
    ).round(2)

    away = team_matches.merge(primary_venues[["team", "venue"]], on=["team", "venue"], how="left", indicator=True)
    away = away[away["_merge"] == "left_only"]
    away_summary = away.groupby("team", as_index=False).agg(away_matches=("played", "sum"), away_wins=("wins", "sum"))
    away_summary["away_win_pct"] = np.where(
        away_summary["away_matches"] > 0,
        away_summary["away_wins"] / away_summary["away_matches"] * 100,
        0,
    ).round(2)

    chase = roles[roles["chasing_team"].notna()].groupby("chasing_team", as_index=False).agg(
        chasing_matches=("match_id", "count"),
        chasing_wins=("chasing_win", "sum"),
    ).rename(columns={"chasing_team": "team"})
    chase["chasing_strength_score"] = np.where(chase["chasing_matches"] > 0, chase["chasing_wins"] / chase["chasing_matches"] * 100, 0).round(2)

    defend = roles[roles["batting_first"].notna()].groupby("batting_first", as_index=False).agg(
        defending_matches=("match_id", "count"),
        defending_wins=("defending_win", "sum"),
    ).rename(columns={"batting_first": "team"})
    defend["defending_strength_score"] = np.where(defend["defending_matches"] > 0, defend["defending_wins"] / defend["defending_matches"] * 100, 0).round(2)

    seasonal = season_win_rates(matches)
    consistency = seasonal.groupby("team", as_index=False).agg(
        season_win_pct_std=("win_pct", "std"),
        seasons=("season", "nunique"),
    ).fillna({"season_win_pct_std": 0})
    consistency["team_consistency_index"] = (100 - consistency["season_win_pct_std"]).clip(lower=0).round(2)

    phase = deliveries.groupby(["batting_team", "phase"], as_index=False).agg(runs=("total_runs", "sum"), balls=("legal_ball", "sum"))
    phase["run_rate"] = np.where(phase["balls"] > 0, phase["runs"] / phase["balls"] * 6, 0)
    best_phase = phase[phase["balls"] >= 60].sort_values(["batting_team", "run_rate"], ascending=[True, False]).drop_duplicates("batting_team")
    best_phase = best_phase.rename(columns={"batting_team": "team", "phase": "best_phase", "run_rate": "best_phase_run_rate"})

    output = (
        base.merge(home_summary[["team", "home_advantage_score"]], on="team", how="left")
        .merge(away_summary[["team", "away_win_pct"]], on="team", how="left")
        .merge(chase[["team", "chasing_strength_score"]], on="team", how="left")
        .merge(defend[["team", "defending_strength_score"]], on="team", how="left")
        .merge(consistency[["team", "team_consistency_index"]], on="team", how="left")
        .merge(best_phase[["team", "best_phase", "best_phase_run_rate"]], on="team", how="left")
    )
    return output.fillna({"home_advantage_score": 0, "away_win_pct": 0, "chasing_strength_score": 0, "defending_strength_score": 0, "team_consistency_index": 0, "best_phase": "Unknown", "best_phase_run_rate": 0}).sort_values("win_pct", ascending=False)


def team_phase_performance(deliveries: pd.DataFrame) -> pd.DataFrame:
    """Return team run rate by powerplay, middle, and death phases."""
    if deliveries.empty:
        return pd.DataFrame()
    grouped = deliveries.groupby(["batting_team", "phase"], as_index=False).agg(runs=("total_runs", "sum"), balls=("legal_ball", "sum"))
    grouped["run_rate"] = np.where(grouped["balls"] > 0, grouped["runs"] / grouped["balls"] * 6, 0).round(2)
    return grouped.rename(columns={"batting_team": "team"}).sort_values(["team", "run_rate"], ascending=[True, False])


def player_impact_scores(deliveries: pd.DataFrame, matches: pd.DataFrame | None = None, min_balls: int = 120) -> pd.DataFrame:
    """Compute batting impact, consistency, and pressure performance scores."""
    if deliveries.empty:
        return pd.DataFrame()
    batting = batting_leaderboard(deliveries, min_balls=min_balls)
    if batting.empty:
        return batting

    per_match = deliveries.groupby(["batter", "match_id"], as_index=False).agg(match_runs=("batter_runs", "sum"))
    win_context = deliveries[["match_id", "batting_team", "winner", "batter"]].drop_duplicates()
    win_context["player_team_won"] = win_context["batting_team"].eq(win_context["winner"])
    match_wins = per_match.merge(win_context[["batter", "match_id", "player_team_won"]], on=["batter", "match_id"], how="left")
    winning = match_wins.groupby("batter", as_index=False).agg(
        match_winning_runs=("match_runs", lambda s: float(s[match_wins.loc[s.index, "player_team_won"].fillna(False)].sum())),
        high_impact_innings=("match_runs", lambda s: int((s >= 40).sum())),
    )

    pressure = deliveries[deliveries["is_pressure_match"]].groupby("batter", as_index=False).agg(
        pressure_runs=("batter_runs", "sum"),
        pressure_balls=("legal_ball", "sum"),
    )
    pressure["pressure_strike_rate"] = np.where(pressure["pressure_balls"] > 0, pressure["pressure_runs"] / pressure["pressure_balls"] * 100, 0)

    scored = batting.merge(winning, on="batter", how="left").merge(pressure, on="batter", how="left").fillna(0)
    for source, target in [
        ("runs", "normalized_runs"),
        ("strike_rate", "strike_rate_weight"),
        ("boundary_pct", "boundary_weight"),
        ("match_winning_runs", "match_winning_contribution"),
    ]:
        max_value = scored[source].max()
        scored[target] = np.where(max_value > 0, scored[source] / max_value * 100, 0)
    scored["impact_score"] = (
        scored["normalized_runs"] * 0.35
        + scored["strike_rate_weight"] * 0.20
        + scored["boundary_weight"] * 0.20
        + scored["match_winning_contribution"] * 0.25
    ).round(2)
    scored["consistency_score"] = scored["consistency_index"].rank(pct=True).mul(100).round(2)
    scored["pressure_performance_score"] = np.where(
        scored["pressure_balls"] >= 24,
        (scored["pressure_runs"].rank(pct=True) * 60 + scored["pressure_strike_rate"].rank(pct=True) * 40),
        0,
    ).round(2)
    return scored.sort_values("impact_score", ascending=False)


def phase_batting_leaderboard(deliveries: pd.DataFrame, phase: str, min_balls: int = 60) -> pd.DataFrame:
    """Return best batters in a selected innings phase."""
    if deliveries.empty:
        return pd.DataFrame()
    phase_df = deliveries[deliveries["phase"].eq(phase)]
    return batting_leaderboard(phase_df, min_balls=min_balls)


def phase_bowling_leaderboard(deliveries: pd.DataFrame, phase: str, min_overs: float = 8.0) -> pd.DataFrame:
    """Return best bowlers in a selected innings phase."""
    if deliveries.empty:
        return pd.DataFrame()
    phase_df = deliveries[deliveries["phase"].eq(phase)]
    bowlers = bowling_leaderboard(phase_df, min_overs=min_overs)
    if bowlers.empty:
        return bowlers
    bowlers["bowling_impact_score"] = (
        bowlers["wickets"].rank(pct=True) * 60
        + (1 - bowlers["economy"].rank(pct=True)) * 40
    ).round(2)
    return bowlers.sort_values(["bowling_impact_score", "wickets"], ascending=False)


def venue_advanced_insights(matches: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Compute venue batting, bowling, toss, chase, and bias metrics."""
    if matches.empty or deliveries.empty:
        return pd.DataFrame()
    innings_scores = deliveries.groupby(["match_id", "venue", "innings_number"], as_index=False).agg(
        score=("total_runs", "sum"),
        wickets=("is_wicket", "sum"),
        balls=("legal_ball", "sum"),
    )
    venue_base = innings_scores.groupby("venue", as_index=False).agg(
        matches=("match_id", "nunique"),
        avg_innings_score=("score", "mean"),
        wickets_per_innings=("wickets", "mean"),
        avg_first_innings_score=("score", lambda s: np.nan),
    )
    first = innings_scores[innings_scores["innings_number"] == 1].groupby("venue", as_index=False).agg(avg_first_innings_score=("score", "mean"))
    second = innings_scores[innings_scores["innings_number"] == 2].groupby("venue", as_index=False).agg(avg_second_innings_score=("score", "mean"))

    roles = match_innings_roles(matches, deliveries)
    outcome = roles.groupby("venue", as_index=False).agg(
        toss_influence_pct=("toss_winner_won", "mean"),
        chasing_success_pct=("chasing_win", "mean"),
    )
    venue = venue_base.drop(columns=["avg_first_innings_score"]).merge(first, on="venue", how="left").merge(second, on="venue", how="left").merge(outcome, on="venue", how="left")
    league_score = venue["avg_innings_score"].mean()
    league_wickets = venue["wickets_per_innings"].mean()
    venue["batting_friendly_index"] = np.where(league_score > 0, venue["avg_innings_score"] / league_score * 100, 0).round(2)
    venue["bowling_friendly_index"] = np.where(league_wickets > 0, venue["wickets_per_innings"] / league_wickets * 100, 0).round(2)
    venue["toss_influence_pct"] = (venue["toss_influence_pct"].fillna(0) * 100).round(2)
    venue["chasing_success_pct"] = (venue["chasing_success_pct"].fillna(0) * 100).round(2)
    venue["venue_bias_score"] = (venue["chasing_success_pct"] - 50).abs().add((venue["toss_influence_pct"] - 50).abs()).round(2)
    for column in ("avg_innings_score", "wickets_per_innings", "avg_first_innings_score", "avg_second_innings_score"):
        venue[column] = venue[column].round(2)
    return venue.sort_values(["matches", "batting_friendly_index"], ascending=False)
