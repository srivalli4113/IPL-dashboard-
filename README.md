# IPL Analytics Platform + AI Analyst

Fault-tolerant IPL analytics dashboard built with Streamlit, Pandas, NumPy, and Plotly using the Cricsheet IPL JSON dataset.

## Features

- Interactive IPL dashboard with team, player, toss, venue, and phase analytics
- Contextual season, team, and player filters
- Player drilldown showing teams played for, venues, match analytics, and peak performance charts
- Advanced team metrics including home advantage, chasing strength, defending strength, and consistency
- Player impact scores, batting leaderboards, bowling leaderboards, and phase specialists
- AI Generated Insights and Ask IPL AI query assistant
- Dataset-grounded AI answers with verification badge, detected intent, applied filters, metrics used, records analysed, source, and validation status
- Fault-tolerant data quality pipeline and validation reports
- Automated tests for core analytics correctness

## Project Structure

```text
ipl_analytics_dashboard/
├── app.py
├── requirements.txt
├── README.md
├── REPORT.md
├── validation_report.md
├── test_results.md
├── data/
│   ├── raw/
│   └── processed/
├── logs/
├── src/
└── tests/
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Dataset Placement

Download the IPL JSON dataset from Cricsheet and place the extracted `.json` files in:

```text
data/raw/
```

The repository intentionally excludes raw JSON and processed parquet files to keep the submission lightweight.

## Run

```bash
streamlit run app.py
```

## Tests

```bash
python -m unittest discover tests
```

ted questions return an insufficient-data response.
