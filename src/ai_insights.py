"""Automated, dataset-grounded insight generation for the IPL dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics import match_innings_roles, phase_scoring, season_win_rates, venue_advanced_insights


def _safe_pct(value: float) -> str:
    return f"{float(value):.1f}%"


def generate_ai_insights(matches: pd.DataFrame, deliveries: pd.DataFrame, limit: int = 8) -> list[str]:
    """Generate human-readable insights from actual computed statistics."""
    if matches.empty or deliveries.empty:
        return ["No insights are available because the current filters returned no data."]

    insights: list[str] = []
    roles = match_innings_roles(matches, deliveries)
    if not roles.empty:
        chase_rate = roles["chasing_win"].mean() * 100
        insights.append(f"Chasing teams win {_safe_pct(chase_rate)} of result matches in the selected data.")

        toss_rate = roles["toss_winner_won"].mean() * 100
        insights.append(f"Toss winners convert the toss into a match win {_safe_pct(toss_rate)} of the time.")

    phase = phase_scoring(deliveries)
    if not phase.empty and phase["season"].nunique() >= 2:
        death = phase[phase["phase"].eq("Death Overs")].sort_values("season")
        if len(death) >= 2 and death.iloc[0]["run_rate"] > 0:
            change = (death.iloc[-1]["run_rate"] - death.iloc[0]["run_rate"]) / death.iloc[0]["run_rate"] * 100
            insights.append(
                f"Death-over run rate changed by {change:+.1f}% from {death.iloc[0]['season']} to {death.iloc[-1]['season']}."
            )

    seasonal = season_win_rates(matches)
    if not seasonal.empty:
        latest = str(sorted(seasonal["season"].astype(str).unique())[-1])
        latest_best = seasonal[seasonal["season"].astype(str).eq(latest)].sort_values("win_pct", ascending=False).head(1)
        if not latest_best.empty:
            row = latest_best.iloc[0]
            insights.append(f"{row['team']} had the highest selected-season win rate in {latest} at {_safe_pct(row['win_pct'])}.")

    venues = venue_advanced_insights(matches, deliveries)
    if not venues.empty:
        batting = venues[venues["matches"] >= 5].sort_values("batting_friendly_index", ascending=False).head(1)
        bowling = venues[venues["matches"] >= 5].sort_values("bowling_friendly_index", ascending=False).head(1)
        chase = venues[venues["matches"] >= 5].sort_values("chasing_success_pct", ascending=False).head(1)
        if not batting.empty:
            row = batting.iloc[0]
            insights.append(f"{row['venue']} is the strongest batting venue by index ({row['batting_friendly_index']:.1f}) among venues with 5+ matches.")
        if not bowling.empty:
            row = bowling.iloc[0]
            insights.append(f"{row['venue']} is the strongest bowling-friendly venue by wicket index ({row['bowling_friendly_index']:.1f}).")
        if not chase.empty:
            row = chase.iloc[0]
            insights.append(f"Chasing is most successful at {row['venue']} in this selection, with a {_safe_pct(row['chasing_success_pct'])} success rate.")

    team_years = season_win_rates(matches)
    if not team_years.empty and team_years["season"].nunique() >= 4:
        candidate_rows = []
        for team, group in team_years.groupby("team"):
            ordered = group.sort_values("season")
            if len(ordered) >= 4:
                early = ordered.head(max(1, len(ordered) // 2))["win_pct"].mean()
                recent = ordered.tail(max(1, len(ordered) // 2))["win_pct"].mean()
                candidate_rows.append((team, recent - early))
        if candidate_rows:
            team, delta = max(candidate_rows, key=lambda item: item[1])
            insights.append(f"{team} shows the largest recent improvement in win percentage, up {delta:.1f} points versus its earlier selected seasons.")

    run_rate_by_season = deliveries.groupby("season", as_index=False).agg(runs=("total_runs", "sum"), balls=("legal_ball", "sum"))
    run_rate_by_season["run_rate"] = np.where(run_rate_by_season["balls"] > 0, run_rate_by_season["runs"] / run_rate_by_season["balls"] * 6, 0)
    if len(run_rate_by_season) >= 2:
        best = run_rate_by_season.sort_values("run_rate", ascending=False).iloc[0]
        insights.append(f"{best['season']} is the highest-scoring selected season by run rate at {best['run_rate']:.2f} runs per over.")

    return insights[:limit]
