"""Deterministic validation tests for core IPL analytics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.analytics import (
    batting_leaderboard,
    bowling_leaderboard,
    team_win_rates,
    toss_impact,
    venue_trends,
    player_impact_scores,
)
from src.data_quality import run_data_quality_pipeline
from src.query_router import INSUFFICIENT_ANSWER, route_query


def fixture_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = pd.DataFrame(
        [
            {"match_id": "m1", "season": "2024", "date": pd.Timestamp("2024-01-01"), "venue": "Venue A", "teams": ["Team A", "Team B"], "winner": "Team A", "toss_winner": "Team A", "toss_decision": "field"},
            {"match_id": "m2", "season": "2024", "date": pd.Timestamp("2024-01-02"), "venue": "Venue A", "teams": ["Team A", "Team B"], "winner": "Team A", "toss_winner": "Team B", "toss_decision": "bat"},
            {"match_id": "m3", "season": "2024", "date": pd.Timestamp("2024-01-03"), "venue": "Venue B", "teams": ["Team A", "Team B"], "winner": "Team B", "toss_winner": "Team B", "toss_decision": "field"},
        ]
    )

    rows = []

    def add(match_id: str, innings: int, batting: str, bowling: str, venue: str, winner: str, batter: str, bowler: str, runs: list[int], wicket_ball: int | None = None) -> None:
        for idx, run in enumerate(runs, start=1):
            rows.append(
                {
                    "match_id": match_id,
                    "innings_number": innings,
                    "batting_team": batting,
                    "bowling_team": bowling,
                    "over": 0,
                    "ball": idx,
                    "batter": batter,
                    "bowler": bowler,
                    "non_striker": "Partner",
                    "batter_runs": run,
                    "extras": 0,
                    "total_runs": run,
                    "legal_ball": 1,
                    "is_four": int(run == 4),
                    "is_six": int(run == 6),
                    "is_wicket": int(wicket_ball == idx),
                    "player_out": batter if wicket_ball == idx else "Unknown",
                    "dismissed_player": batter if wicket_ball == idx else "Unknown",
                    "wicket_kind": "caught" if wicket_ball == idx else "Unknown",
                    "season": "2024",
                    "venue": venue,
                    "winner": winner,
                    "is_pressure_match": False,
                    "phase": "Powerplay",
                }
            )

    add("m1", 1, "Team B", "Team A", "Venue A", "Team A", "B Batter", "A Bowler", [1, 1, 1, 1, 1, 1], wicket_ball=6)
    add("m1", 2, "Team A", "Team B", "Venue A", "Team A", "A Batter", "B Bowler", [4, 4, 4, 0, 0, 0])
    add("m2", 1, "Team A", "Team B", "Venue A", "Team A", "A Batter", "B Bowler", [6, 1, 1, 1, 1, 1])
    add("m2", 2, "Team B", "Team A", "Venue A", "Team A", "B Batter", "A Bowler", [1, 1, 1, 1, 1, 1], wicket_ball=3)
    add("m3", 1, "Team A", "Team B", "Venue B", "Team B", "A Batter", "B Bowler", [1, 1, 1, 1, 1, 1], wicket_ball=6)
    add("m3", 2, "Team B", "Team A", "Venue B", "Team B", "B Batter", "A Bowler", [2, 2, 2, 2, 2, 2])
    return matches, pd.DataFrame(rows)


class AnalyticsValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matches, self.deliveries = fixture_tables()

    def test_win_rate_calculation(self) -> None:
        rates = team_win_rates(self.matches).set_index("team")
        self.assertEqual(rates.loc["Team A", "matches"], 3)
        self.assertEqual(rates.loc["Team A", "wins"], 2)
        self.assertAlmostEqual(rates.loc["Team A", "win_pct"], 66.67, places=2)

    def test_toss_calculation(self) -> None:
        toss = toss_impact(self.matches).set_index("toss_decision")
        self.assertAlmostEqual(toss.loc["field", "toss_win_match_win_pct"], 100.0, places=2)
        self.assertAlmostEqual(toss.loc["bat", "toss_win_match_win_pct"], 0.0, places=2)

    def test_venue_calculation(self) -> None:
        venues = venue_trends(self.matches, self.deliveries).set_index("venue")
        self.assertAlmostEqual(venues.loc["Venue A", "avg_first_innings_score"], 8.5, places=2)
        self.assertAlmostEqual(venues.loc["Venue A", "chase_success_rate"], 50.0, places=2)

    def test_batting_and_bowling_rates(self) -> None:
        batting = batting_leaderboard(self.deliveries, min_balls=1).set_index("batter")
        self.assertEqual(batting.loc["A Batter", "runs"], 29)
        self.assertEqual(batting.loc["A Batter", "dismissals"], 1)
        self.assertAlmostEqual(batting.loc["A Batter", "batting_average"], 29.0, places=2)
        self.assertAlmostEqual(batting.loc["A Batter", "strike_rate"], 161.11, places=2)

        bowling = bowling_leaderboard(self.deliveries, min_overs=0).set_index("bowler")
        self.assertEqual(bowling.loc["A Bowler", "wickets"], 2)
        self.assertAlmostEqual(bowling.loc["A Bowler", "economy"], 8.0, places=2)
        self.assertAlmostEqual(bowling.loc["A Bowler", "bowling_average"], 12.0, places=2)

    def test_impact_score_is_reproducible(self) -> None:
        impact = player_impact_scores(self.deliveries, min_balls=1)
        self.assertFalse(impact.empty)
        self.assertIn("impact_score", impact.columns)
        self.assertTrue(impact["impact_score"].between(0, 100).all())

    def test_query_routing_and_unknown_answer(self) -> None:
        result = route_query("Does winning the toss matter?", self.matches, self.deliveries)
        self.assertEqual(result.intent, "toss_analysis")
        self.assertEqual(result.verification_badge, "Verified Dataset Result")
        self.assertGreater(result.records_analysed, 0)

        unknown = route_query("What is the humidity advantage?", self.matches, self.deliveries)
        self.assertEqual(unknown.answer, INSUFFICIENT_ANSWER)
        self.assertEqual(unknown.verification_badge, "Insufficient Data")

    def test_data_validation_pipeline(self) -> None:
        valid_record = {
            "meta": {},
            "info": {
                "dates": ["2024-01-01"],
                "teams": ["Team A", "Team B"],
                "venue": "Venue A",
                "event": {"name": "Test League"},
                "match_type": "T20",
                "gender": "male",
                "players": {"Team A": ["A"], "Team B": ["B"]},
                "toss": {"winner": "Team A", "decision": "bat"},
            },
            "innings": [{"team": "Team A", "overs": []}],
        }
        invalid_record = {"meta": {}, "info": {"teams": ["Team A"]}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "valid.json").write_text(json.dumps(valid_record), encoding="utf-8")
            (root / "invalid.json").write_text(json.dumps(invalid_record), encoding="utf-8")
            report = run_data_quality_pipeline(root)
        self.assertEqual(report.total_files_processed, 2)
        self.assertEqual(report.valid_files, 1)
        self.assertEqual(report.invalid_files, 1)
        self.assertEqual(report.records_skipped, 1)


if __name__ == "__main__":
    unittest.main()
