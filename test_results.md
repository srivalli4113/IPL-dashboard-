# Test Results

Command:

```bash
.venv/bin/python -m unittest discover tests
```

Result:

```text
.......
----------------------------------------------------------------------
Ran 7 tests in 0.140s

OK
```

Coverage Summary:

| Test | Purpose |
|---|---|
| `test_win_rate_calculation` | Verifies wins, matches played, and win percentage from exploded match outcomes. |
| `test_toss_calculation` | Verifies toss winner match win percentage by toss decision. |
| `test_venue_calculation` | Verifies average first innings score and chase success percentage. |
| `test_batting_and_bowling_rates` | Verifies batting runs, dismissals, batting average, economy, and bowling average. |
| `test_impact_score_is_reproducible` | Verifies impact score exists and stays bounded from 0 to 100. |
| `test_query_routing_and_unknown_answer` | Verifies supported query routing and unsupported-query insufficient-data behavior. |
| `test_data_validation_pipeline` | Verifies valid/invalid JSON validation counts. |

Validation Position:

These tests use small deterministic fixtures so expected values can be calculated by hand. They validate formulas and edge-case behavior rather than visual layout.
