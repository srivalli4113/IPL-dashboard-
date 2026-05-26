# IPL Analytics Platform + AI Analyst

## Executive Summary

This project implements a production-oriented IPL Analytics Platform built on top of the Cricsheet IPL JSON dataset.

The solution goes beyond basic visualization by incorporating:

- Fault-tolerant ingestion
- Schema validation
- Data quality monitoring
- Advanced cricket analytics
- Automated insight generation
- Deterministic natural-language analytics assistant
- Interactive Streamlit dashboard

The platform is designed to process imperfect datasets safely while generating meaningful cricket insights across teams, players, venues, and match outcomes.

---

# System Architecture

                    ┌─────────────────────┐
                    │ Cricsheet IPL JSON  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Fault-Tolerant      │
                    │ Data Loader         │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Schema Validation   │
                    │ Data Quality Layer  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Data Cleaning       │
                    │ Normalization       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Analytics Engine    │
                    └─────┬─────────┬─────┘
                          │         │
                ┌─────────▼───┐ ┌──▼─────────┐
                │ AI Insights │ │ Query AI   │
                └─────────┬───┘ └──┬─────────┘
                          │         │
                          └────┬────┘
                               ▼
                    ┌─────────────────────┐
                    │ Streamlit Dashboard │
                    └─────────────────────┘

---

# Technology Stack

## Frontend

- Streamlit
- Plotly

## Analytics

- Pandas
- NumPy

## Data Processing

- JSON
- Python

## Logging

- Python Logging Framework

## Development Tools

- ChatGPT
- Codex

---

# Project Structure

(project tree)

---

# Dataset Selection

## Dataset

Cricsheet IPL Dataset

## Format Chosen

JSON

## Reasoning

JSON was selected because:

- Hierarchical structure
- Better schema validation
- Easier fault isolation
- Better support for nested deliveries

---

# Data Pipeline Design

## Stage 1: Data Ingestion

Responsibilities:

- File discovery
- JSON loading
- Corrupt file detection
- Logging

Fault Handling:

- Corrupt files skipped
- Processing continues

---

## Stage 2: Schema Validation

Validation checks:

- Match metadata
- Teams
- Innings
- Deliveries
- Venue
- Toss information

Failures:

- Logged
- Isolated
- Reported

---

## Stage 3: Data Quality Layer

Metrics tracked:

- Total files processed
- Successful files
- Failed files
- Missing fields
- Duplicate matches
- Invalid deliveries
- Schema violations

Generated reports:

- Quality summary
- Validation logs

---

## Stage 4: Data Cleaning

Operations:

- Missing value handling
- Type normalization
- Duplicate removal
- Field standardization

---

## Stage 5: Analytical Transformation

Generated tables:

### Matches

- Match outcomes
- Toss results
- Venue information

### Deliveries

- Ball-by-ball data

### Batting Metrics

- Runs
- Strike Rate
- Average

### Bowling Metrics

- Wickets
- Economy
- Bowling Average

---

# Fault Tolerance Strategy

## Objective

Ensure platform stability despite imperfect data.

## Scenario 1

Corrupted JSON

Action:

- Skip file
- Log error

Result:

Pipeline continues

---

## Scenario 2

Missing Toss Data

Action:

- Replace with Unknown

Result:

Match retained

---

## Scenario 3

Incomplete Deliveries

Action:

- Skip affected delivery

Result:

Match remains analyzable

---

## Scenario 4

Unexpected Schema Changes

Action:

- Safe extraction
- Fallback defaults

Result:

No crash

---

# Dashboard Design

## Overview Page

Provides:

- Total matches
- Total seasons
- Teams
- Venues
- KPI summaries

---

## Team Analytics

Metrics:

- Win Rate
- Home Advantage
- Away Performance
- Chasing Success
- Defending Success
- Consistency Index

Visualizations:

- Win percentage charts
- Seasonal trend analysis

---

## Player Analytics

### Batting

- Runs
- Strike Rate
- Average

### Bowling

- Wickets
- Economy
- Average

### Advanced Metrics

- Impact Score
- Consistency Score
- Pressure Score

---

## Toss Analysis

Evaluates:

- Toss winner impact
- Toss decision trends
- Venue-specific toss effects

---

## Venue Analytics

Evaluates:

- Average scores
- Chasing success
- Toss influence
- Venue bias

---

# AI Generated Insights

## Purpose

Automatically identify notable patterns within the dataset.

Examples:

- Best venue for chasing
- Most dominant team
- Highest impact player
- Strongest bowling venue

Insights are generated from computed statistics.

No fabricated information is produced.

---

# Ask IPL AI

## Purpose

Enable natural-language access to analytics.

Examples:

- Who has the highest strike rate?
- Which team dominates at Wankhede?
- Does toss winning matter?

---

## Query Processing Pipeline

User Question
↓
Intent Detection
↓
Filter Extraction
↓
Analytics Function Routing
↓
Pandas Computation
↓
Verified Result

The assistant does not use generative cricket facts.

All responses originate from dataset-derived analytics.

---

# Required Analysis Coverage

## Win Rates by Team

Implemented

Metrics:

- Overall win rate
- Seasonal win rate

---

## Best Batsmen

Implemented

Metrics:

- Runs
- Strike Rate
- Average

---

## Best Bowlers

Implemented

Metrics:

- Wickets
- Economy
- Average

---

## Toss Impact

Implemented

Metrics:

- Toss winner
- Toss decision
- Match result

---

## Venue Trends

Implemented

Metrics:

- Venue success rate
- Average score
- Chase percentage

---

# Generalization Strategy

The solution does not hardcode:

- Teams
- Players
- Venues
- Seasons

All entities are discovered dynamically.

The platform can process future IPL datasets without modification.

---

# External Services and Cost Analysis

## Runtime Dependencies

- Cricsheet Dataset
- Streamlit
- Plotly
- Pandas

## Development Tools

### ChatGPT

Used for:

- Architecture review
- Documentation support

### Claude

Used for:

- Design validation
- Technical review

### Codex

Used for:

- Code generation assistance
- Refactoring support

## Cost Impact

Runtime Cost: ₹0

API Cost During Execution: ₹0

Cloud Dependency: None

AI Dependency During Execution: None

The deployed dashboard operates entirely offline.

---

# Testing and Validation

Testing included:

- Corrupted files
- Missing fields
- Duplicate records
- Partial innings
- Schema deviations

Results:

- No pipeline crashes
- Accurate analytical outputs
- Stable dashboard performance

---

# Key Findings

- Toss winning offers a moderate advantage.
- Venue conditions significantly influence chasing success.
- Consistent players outperform purely aggressive players.
- Bowling effectiveness depends on both economy and wicket-taking ability.
- Team dominance fluctuates across seasons.

---

# Conclusion

The IPL Analytics Platform successfully delivers a fault-tolerant, scalable, and interactive analytics solution on top of the Cricsheet IPL dataset.

The platform satisfies all required assignment objectives while extending functionality through data quality monitoring, advanced cricket metrics, automated insights, and deterministic natural-language analytics.