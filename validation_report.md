# Validation Report

This report documents the formulas, assumptions, edge cases, and validation approach for every core metric in the IPL Analytics Platform.

## Win Rate

Formula:

```text
wins / matches_played * 100
```

Assumptions:

- One match contributes one appearance to each team in the `teams` list.
- Matches with `winner = Unknown` count as played but not won.

Edge cases:

- No-result matches produce zero wins for both teams.
- Missing `teams` values are normalized to an empty list during cleaning.

Validation:

- Cross-checked against exploded team-match rows.
- Covered by `test_win_rate_calculation`.

## Toss Winner Match Win %

Formula:

```text
toss_winner_match_wins / matches_with_known_toss_and_winner * 100
```

Assumptions:

- Toss records with `Unknown` winner or match winner are excluded.
- Results are grouped by toss decision where available.

Edge cases:

- Abandoned/no-result matches are excluded from toss impact percentages.
- Missing toss metadata is logged by the data quality layer.

Validation:

- Cross-checked against known toss winner and match winner pairs.
- Covered by `test_toss_calculation`.

## Venue Chase Success %

Formula:

```text
matches_won_by_second_batting_team / completed_matches_at_venue * 100
```

Assumptions:

- Innings 1 is the defending side.
- Innings 2 is the chasing side.
- Only completed matches with known winners are considered.

Edge cases:

- Matches without a second innings are treated as not successful chases for score aggregation and are protected against nullable boolean errors.
- Missing venue values are normalized to `Unknown`.

Validation:

- Cross-checked using match innings roles and venue-level aggregation.
- Covered by `test_venue_calculation`.

## Average First Innings Score

Formula:

```text
sum(first_innings_runs_at_venue) / first_innings_count_at_venue
```

Assumptions:

- Delivery `total_runs` is used for innings score.
- Super-over and unusual innings are retained if they appear as innings rows.

Edge cases:

- Venues with no first innings return no row.
- Partial matches are included only for innings that exist.

Validation:

- Cross-checked against manually computed fixture innings totals.
- Covered by `test_venue_calculation`.

## Batting Strike Rate

Formula:

```text
batter_runs / legal_balls_faced * 100
```

Assumptions:

- Wides and no-balls are not legal balls.
- Batter runs exclude extras.

Edge cases:

- Zero legal balls produces strike rate `0`.
- Minimum-ball thresholds remove noisy players from leaderboards.

Validation:

- Cross-checked against grouped batter runs and legal balls.
- Covered by `test_batting_and_bowling_rates`.

## Batting Average

Formula:

```text
batter_runs / dismissals
```

Assumptions:

- Dismissals are counted from `dismissed_player`.
- `retired hurt` is excluded as a dismissal.

Edge cases:

- Zero dismissals returns `NaN`, which is preferred to a misleading infinite value.

Validation:

- Cross-checked against dismissed player rows in deterministic fixtures.
- Covered by `test_batting_and_bowling_rates`.

## Bowling Economy

Formula:

```text
runs_conceded / legal_balls_bowled * 6
```

Assumptions:

- Runs conceded use delivery `total_runs`; this is analytically consistent but can differ slightly from official scorecards for extras attribution.
- Wides and no-balls are not legal balls.

Edge cases:

- Zero legal balls produces economy `0`.
- Minimum-over thresholds remove noisy bowlers from leaderboards.

Validation:

- Cross-checked against grouped bowler balls and runs conceded.
- Covered by `test_batting_and_bowling_rates`.

## Bowling Average

Formula:

```text
runs_conceded / bowler_wickets
```

Assumptions:

- Bowler wickets exclude run out, retired hurt, retired out, and obstructing the field.

Edge cases:

- Zero wickets returns `NaN`.

Validation:

- Cross-checked against wicket kinds in deterministic fixtures.
- Covered by `test_batting_and_bowling_rates`.

## Team Consistency Index

Formula:

```text
100 - standard_deviation(season_win_pct)
```

Assumptions:

- Higher values indicate more stable season-to-season win rates.
- A team with one selected season has standard deviation filled as zero.

Edge cases:

- Values are clipped at zero to avoid negative consistency scores.

Validation:

- Calculated from season win-rate output, which is itself derived from exploded match outcomes.

## Home Advantage Score

Formula:

```text
wins_at_primary_venue / matches_at_primary_venue * 100
```

Assumptions:

- Primary venue is inferred as the venue where a team appears most often in the selected data.
- This is an inferred home signal because Cricsheet does not provide an explicit home/away flag.

Edge cases:

- Neutral tournaments or venue-shifted seasons may weaken the interpretation.

Validation:

- Reproducible from team-venue match counts and winners.

## Chasing Efficiency

Formula:

```text
team_wins_while_chasing / team_matches_while_chasing * 100
```

Assumptions:

- Second innings batting team is the chasing team.

Edge cases:

- Incomplete second innings rows are excluded from chasing-team grouping.

Validation:

- Derived from `match_innings_roles()`.

## Defending Efficiency

Formula:

```text
team_wins_while_batting_first / team_matches_batting_first * 100
```

Assumptions:

- First innings batting team is the defending team.

Edge cases:

- Matches without known winners are excluded from role outcome calculations.

Validation:

- Derived from `match_innings_roles()`.

## Venue Bias Index

Formula:

```text
abs(chasing_success_pct - 50) + abs(toss_influence_pct - 50)
```

Assumptions:

- A neutral venue should be near 50% for both chasing success and toss winner success.
- Larger values indicate stronger directional bias.

Edge cases:

- Small venue sample sizes can exaggerate bias.

Validation:

- Built from toss and chasing outcome calculations.
- Covered indirectly by venue and toss tests.

## Player Impact Score

Formula:

```text
0.35 * normalized_runs
+ 0.20 * strike_rate_weight
+ 0.20 * boundary_weight
+ 0.25 * match_winning_contribution
```

Assumptions:

- Components are normalized to a 0-100 scale within the current filter context.
- Match-winning contribution is runs scored in matches won by the batter's team.

Edge cases:

- Empty or threshold-filtered datasets return an empty table.
- Scores are context-relative, so changing filters changes normalization.

Validation:

- Ensures score is present and bounded between 0 and 100.
- Covered by `test_impact_score_is_reproducible`.

## Query Verification

Formula:

```text
natural_language_query -> detected_intent -> deterministic_analytics_function -> verified_result
```

Assumptions:

- The router may classify query intent, but it never fabricates metric values.
- Unsupported questions return the exact insufficient-data response.

Edge cases:

- Unknown entities or unsupported concepts produce `Insufficient Data`.

Validation:

- Covered by `test_query_routing_and_unknown_answer`.

## Data Quality Percentage

Formula:

```text
valid_files / total_files_processed * 100
```

Assumptions:

- Each raw JSON file represents one match-level record.

Edge cases:

- Empty raw directory returns 0%.
- Corrupt JSON, missing required fields, and invalid root types are rejected.

Validation:

- Covered by `test_data_validation_pipeline`.
