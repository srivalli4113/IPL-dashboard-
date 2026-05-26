"""Streamlit entrypoint for the IPL Analytics Dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.analytics import (
    NON_BOWLER_WICKET_KINDS,
    batting_leaderboard,
    bowling_leaderboard,
    chase_vs_defend,
    filter_by_season,
    filter_by_team_matches,
    overview_metrics,
    phase_scoring,
    pressure_match_summary,
    phase_batting_leaderboard,
    phase_bowling_leaderboard,
    player_impact_scores,
    team_peak_snapshot,
    team_advanced_insights,
    team_phase_performance,
    season_win_rates,
    team_momentum,
    team_win_rates,
    toss_impact,
    venue_advanced_insights,
    venue_trends,
)
from src.ai_insights import generate_ai_insights
from src.query_router import route_query
from src.transformer import build_analytical_tables, save_processed_tables
from src.utils import RAW_DATA_DIR, configure_logging, ensure_directories
from src.visualizations import (
    donut_chart,
    grouped_bar_chart,
    heatmap_chart,
    histogram,
    horizontal_bar_chart,
    line_chart,
)

logger = configure_logging(__name__)


st.set_page_config(
    page_title="IPL Analytics Dashboard",
    page_icon="IP",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_style(dark_mode: bool = False) -> None:
    app_bg = "#0f172a" if dark_mode else "#f8fafc"
    panel_bg = "#111827" if dark_mode else "#ffffff"
    text = "#e5e7eb" if dark_mode else "#111827"
    heading = "#f8fafc" if dark_mode else "#0f172a"
    border = "#334155" if dark_mode else "#e5e7eb"
    note_bg = "#164e63" if dark_mode else "#ecfeff"
    note_text = "#cffafe" if dark_mode else "#164e63"
    st.markdown(
        f"""
        <style>
        .stApp {{background: {app_bg}; color: {text};}}
        .block-container {{
            max-width: 1280px;
            padding-top: 1.4rem;
            padding-bottom: 2rem;
        }}
        section[data-testid="stSidebar"] {{
            background: {panel_bg};
            border-right: 1px solid {border};
        }}
        [data-testid="stMetric"] {{
            background: {panel_bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
        }}
        h1, h2, h3 {{letter-spacing: 0; color: {heading};}}
        .small-note {{
            color: {text};
            font-size: 0.98rem;
            line-height: 1.55;
        }}
        .section-note {{
            background: {note_bg};
            border-left: 4px solid #0f766e;
            border-radius: 6px;
            color: {note_text};
            padding: 0.85rem 1rem;
            margin: 0.5rem 0 1rem;
        }}
        div[data-testid="stDataFrame"] {{
            border: 1px solid {border};
            border-radius: 8px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner="Building analytical tables from Cricsheet JSON...")
def load_data(raw_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and transform source JSON files with Streamlit caching."""
    matches, deliveries = build_analytical_tables(Path(raw_dir))
    if not matches.empty:
        save_processed_tables(matches, deliveries)
    return matches, deliveries


def chart_config(filename: str = "ipl_chart") -> dict:
    """Return Plotly modebar config with chart download enabled."""
    return {
        "displaylogo": False,
        "toImageButtonOptions": {"format": "png", "filename": filename, "height": 720, "width": 1280, "scale": 2},
    }


def csv_download(label: str, df: pd.DataFrame, filename: str) -> None:
    """Render a CSV download button for a dataframe."""
    if df.empty:
        return
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), filename, "text/csv")


def _all_players(matches: pd.DataFrame) -> list[str]:
    """Return all players found in match metadata."""
    players: set[str] = set()
    if matches.empty or "players" not in matches:
        return []
    for player_map in matches["players"]:
        if not isinstance(player_map, dict):
            continue
        for names in player_map.values():
            if isinstance(names, list):
                players.update(str(name) for name in names if name)
    return sorted(players)


def sidebar_filters(matches: pd.DataFrame) -> tuple[list[str], list[str], str]:
    """Render shared season/team/player filters."""
    st.sidebar.subheader("Filters")
    st.sidebar.caption("Choose All for the full dataset, or narrow the view for a focused comparison.")
    seasons = ["All"]
    teams = ["All"]
    if not matches.empty:
        seasons += sorted(matches["season"].dropna().astype(str).unique().tolist())
        teams += sorted(
            {
                team
                for values in matches["teams"]
                if isinstance(values, list)
                for team in values
            }
        )

    selected_seasons = st.sidebar.multiselect("Season", seasons, default=["All"], help="Filter charts by IPL season.")
    selected_teams = st.sidebar.multiselect("Team", teams, default=["All"], help="Show matches involving selected teams.")
    player_context = filter_by_team_matches(filter_by_season(matches, selected_seasons), selected_teams)
    players = ["All"] + _all_players(player_context)
    selected_player = st.sidebar.selectbox("Player", players, help="Focus player analytics on one player.")
    return selected_seasons, selected_teams, selected_player


def selected_label(values: list[str]) -> str:
    """Return readable selected filter text."""
    if not values or "All" in values:
        return "All"
    if len(values) <= 3:
        return ", ".join(values)
    return f"{len(values)} selected"


def selected_values(values: list[str]) -> list[str]:
    """Return concrete selections, excluding the All sentinel."""
    if not values or "All" in values:
        return []
    return values


def selected_team_rows(df: pd.DataFrame, teams: list[str], column: str = "team") -> pd.DataFrame:
    """Keep only selected teams in an already-aggregated dataframe."""
    chosen = selected_values(teams)
    if df.empty or not chosen or column not in df:
        return df
    return df[df[column].isin(chosen)]


def title_summary(matches: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    """Return selected-team final wins from the current match set."""
    chosen = selected_values(teams)
    if matches.empty or not chosen or "event_stage" not in matches:
        return pd.DataFrame()
    finals = matches[
        matches["event_stage"].str.lower().eq("final")
        & matches["winner"].isin(chosen)
    ].copy()
    return finals[["season", "winner", "venue", "date", "event_stage"]].sort_values("date")


def selected_team_match_outcomes(
    matches: pd.DataFrame,
    deliveries: pd.DataFrame,
    teams: list[str],
) -> pd.DataFrame:
    """Return chasing/defending outcomes for selected teams only."""
    chosen = selected_values(teams)
    if matches.empty or deliveries.empty or not chosen:
        return pd.DataFrame()

    innings_teams = deliveries.groupby(["match_id", "innings_number"], as_index=False).agg(
        team=("batting_team", "first")
    )
    selected_innings = innings_teams[innings_teams["team"].isin(chosen)].copy()
    if selected_innings.empty:
        return pd.DataFrame()

    selected_innings["innings_role"] = selected_innings["innings_number"].map(
        {1: "defending", 2: "chasing"}
    ).fillna("other innings")
    outcomes = selected_innings.merge(matches[["match_id", "winner"]], on="match_id", how="left")
    outcomes["result_type"] = outcomes.apply(
        lambda row: f"{'Won' if row['team'] == row['winner'] else 'Lost'} {row['innings_role']}",
        axis=1,
    )
    return outcomes.groupby("result_type", as_index=False).agg(matches=("match_id", "nunique"))


def season_summary_label(matches: pd.DataFrame) -> str:
    """Return a concise season summary for page headers."""
    seasons = sorted(matches["season"].astype(str).unique())
    if not seasons:
        return "No seasons"
    if len(seasons) <= 4:
        return ", ".join(seasons)
    return f"{seasons[0]} to {seasons[-1]}"


def page_intro(title: str, description: str, matches: pd.DataFrame) -> bool:
    """Render a consistent page heading and filter summary."""
    st.title(title)
    st.markdown(f'<p class="small-note">{description}</p>', unsafe_allow_html=True)
    if matches.empty:
        st.warning("No matches are available for the current filters.")
        return False
    st.markdown(
        f'<div class="section-note">Showing <strong>{matches["match_id"].nunique():,}</strong> matches '
        f'across <strong>{matches["season"].nunique():,}</strong> season(s). '
        f'Visible season range: <strong>{season_summary_label(matches)}</strong></div>',
        unsafe_allow_html=True,
    )
    return True


def readable_table(df: pd.DataFrame, columns: list[str], rename: dict[str, str]) -> pd.DataFrame:
    """Return a polished dataframe for display."""
    if df.empty:
        return df
    return df[columns].rename(columns=rename)


def peak_display_table(peaks: pd.DataFrame) -> pd.DataFrame:
    """Return a compact, viewer-friendly peak snapshot table."""
    if peaks.empty:
        return peaks

    def number(value: object, digits: int = 2) -> str:
        if pd.isna(value):
            return "N/A"
        return f"{float(value):.{digits}f}"

    def whole_number(value: object) -> str:
        if pd.isna(value):
            return "N/A"
        return f"{int(value):,}"

    display = peaks.copy()
    return pd.DataFrame(
        {
            "Team": display["team"],
            "Peak season": display["peak_season"].astype(str),
            "Peak record": display.apply(
                lambda row: f'{whole_number(row["peak_wins"])} wins from {whole_number(row["peak_matches"])} matches ({number(row["peak_win_pct"])}%)',
                axis=1,
            ),
            "Team run rate": display["team_run_rate"].map(number),
            "Peak batter": display.apply(
                lambda row: f'{row["peak_batter"]} ({whole_number(row["batter_runs"])} runs, SR {number(row["batter_strike_rate"])})',
                axis=1,
            ),
            "Batter best season": display.apply(
                lambda row: f'{row["batter_peak_season"]}: {whole_number(row["batter_peak_runs"])} runs, SR {number(row["batter_peak_strike_rate"])}',
                axis=1,
            ),
            "Peak bowler": display.apply(
                lambda row: f'{row["peak_bowler"]} ({whole_number(row["bowler_wickets"])} wickets, Econ {number(row["bowler_economy"])})',
                axis=1,
            ),
            "Strongest phase": display.apply(
                lambda row: f'{row["strongest_phase"]} (RR {number(row["phase_run_rate"])})',
                axis=1,
            ),
        }
    )


def show_data_instructions() -> None:
    """Show first-run guidance when no dataset is present."""
    st.info(
        "No Cricsheet JSON files were found. Download the IPL JSON zip from Cricsheet, "
        "extract it, and place the `.json` files in `data/raw/`."
    )
    st.code("streamlit run app.py", language="bash")


def page_overview(matches: pd.DataFrame, deliveries: pd.DataFrame, teams: list[str]) -> None:
    """Render the overview page."""
    if not page_intro(
        "IPL Analytics Dashboard",
        "A clean view of match volume, teams, players, scoring patterns, and innings outcomes from Cricsheet JSON data.",
        matches,
    ):
        return

    metrics = overview_metrics(matches, deliveries)
    columns = st.columns(6)
    labels = ["Matches", "Seasons", "Venues", "Players", "Runs", "Wickets"]
    keys = ["matches", "seasons", "venues", "players", "runs", "wickets"]
    for column, label, key in zip(columns, labels, keys):
        column.metric(label, f"{metrics[key]:,}")

    win_rates = selected_team_rows(team_win_rates(matches), teams)
    left, right = st.columns((1.2, 1))
    with left:
        st.plotly_chart(
            horizontal_bar_chart(
                win_rates.head(12),
                "team",
                "win_pct",
                "Selected team win rate" if selected_values(teams) else "Top team win rates",
                "Win rate (%)",
            ),
            use_container_width=True,
        )
    with right:
        outcome_data = selected_team_match_outcomes(matches, deliveries, teams)
        if outcome_data.empty:
            outcome_data = chase_vs_defend(matches, deliveries)
        st.plotly_chart(
            donut_chart(
                outcome_data,
                "result_type",
                "matches",
                "Selected team outcomes" if selected_values(teams) else "Wins by innings outcome",
            ),
            use_container_width=True,
        )

    phase = phase_scoring(deliveries)
    st.plotly_chart(
        line_chart(
            phase,
            "season",
            "run_rate",
            "Run rate by match phase",
            "Season",
            "Runs per over",
            color="phase",
        ),
        use_container_width=True,
    )
    st.dataframe(
        readable_table(
            phase.sort_values(["season", "phase"]),
            ["season", "phase", "runs", "balls", "run_rate"],
            {"season": "Season", "phase": "Phase", "runs": "Runs", "balls": "Legal balls", "run_rate": "Run rate"},
        ),
        use_container_width=True,
        hide_index=True,
    )


def page_team_analytics(matches: pd.DataFrame, deliveries: pd.DataFrame, teams: list[str]) -> None:
    """Render team analytics page."""
    if not page_intro(
        "Team Analytics",
        "Compare team results, season performance, and rolling momentum. Horizontal bars keep long team names readable.",
        matches,
    ):
        return
    overall = team_win_rates(matches)
    seasonal = season_win_rates(matches)
    momentum = team_momentum(matches)
    pressure = pressure_match_summary(matches)
    peaks = team_peak_snapshot(matches, deliveries)
    chosen = selected_values(teams)
    if chosen:
        overall = selected_team_rows(overall, teams)
        seasonal = selected_team_rows(seasonal, teams)
        momentum = selected_team_rows(momentum, teams)
        pressure = selected_team_rows(pressure, teams)
        peaks = selected_team_rows(peaks, teams)

        finals = title_summary(matches, teams)
        if not finals.empty:
            winner_names = ", ".join(finals["winner"].unique())
            seasons_won = ", ".join(finals["season"].astype(str).unique())
            st.success(f"{winner_names} won the tournament final in {seasons_won}.")
            st.dataframe(
                readable_table(
                    finals,
                    ["season", "winner", "event_stage", "date", "venue"],
                    {
                        "season": "Season",
                        "winner": "Champion",
                        "event_stage": "Stage",
                        "date": "Date",
                        "venue": "Venue",
                    },
                ),
                use_container_width=True,
                hide_index=True,
            )

    if chosen:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                horizontal_bar_chart(overall.head(15), "team", "win_pct", "Selected team win percentage", "Win rate (%)"),
                use_container_width=True,
            )
        with right:
            if seasonal["season"].nunique() <= 2:
                st.plotly_chart(
                    grouped_bar_chart(
                        seasonal.head(30),
                        "team",
                        "win_pct",
                        "season",
                        "Selected team win rate",
                        "Team",
                        "Win rate (%)",
                    ),
                    use_container_width=True,
                )
            else:
                st.plotly_chart(
                    line_chart(
                        seasonal,
                        "season",
                        "win_pct",
                        "Selected team season trend",
                        "Season",
                        "Win rate (%)",
                        color="team",
                    ),
                    use_container_width=True,
                )
    else:
        st.markdown(
            '<div class="section-note">League view: showing compact summaries only. '
            'Select a team in the sidebar to see one-team season trends and rolling momentum.</div>',
            unsafe_allow_html=True,
        )
        left, right = st.columns((1, 1.15))
        with left:
            st.plotly_chart(
                horizontal_bar_chart(
                    overall.head(12),
                    "team",
                    "win_pct",
                    "Best overall win rates",
                    "Win rate (%)",
                    height=560,
                ),
                use_container_width=True,
            )
        with right:
            top_teams = overall.sort_values("matches", ascending=False).head(10)["team"]
            seasonal_heatmap = seasonal[seasonal["team"].isin(top_teams)]
            st.plotly_chart(
                heatmap_chart(
                    seasonal_heatmap,
                    "season",
                    "team",
                    "win_pct",
                    "Season-wise win rate heatmap",
                    "Season",
                    "Team",
                    height=560,
                ),
                use_container_width=True,
            )

    st.dataframe(
        readable_table(
            overall.head(15) if not chosen else overall,
            ["team", "matches", "wins", "win_pct"],
            {"team": "Team", "matches": "Matches", "wins": "Wins", "win_pct": "Win rate (%)"},
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Peak Career, Player, and Run Rate Snapshot")
    st.markdown(
        '<p class="small-note">This table identifies each team’s best season, scoring run rate in that season, '
        'career-leading batter, that batter’s peak season, leading bowler, and strongest scoring phase.</p>',
        unsafe_allow_html=True,
    )
    if peaks.empty:
        st.caption("No peak snapshot is available for the current filters.")
    else:
        if chosen and len(peaks) == 1:
            peak_row = peaks.iloc[0]
            metric_columns = st.columns(4)
            metric_columns[0].metric("Peak season", str(peak_row["peak_season"]))
            metric_columns[1].metric("Peak win rate", f'{peak_row["peak_win_pct"]:.2f}%')
            metric_columns[2].metric("Team run rate", f'{peak_row["team_run_rate"]:.2f}')
            metric_columns[3].metric("Strongest phase", str(peak_row["strongest_phase"]))

        st.dataframe(
            peak_display_table(peaks.head(15) if not chosen else peaks),
            use_container_width=True,
            hide_index=True,
        )

    if chosen:
        st.plotly_chart(
            line_chart(
                momentum,
                "date",
                "rolling_win_pct",
                "Selected team momentum: rolling 5-match win rate",
                "Match date",
                "Rolling win rate (%)",
                color="team",
                height=520,
            ),
            use_container_width=True,
        )
    else:
        st.info("Rolling momentum is hidden in league view because too many teams make the chart unreadable. Select one team to enable it.")

    st.subheader("Pressure Match Performance")
    if pressure.empty:
        st.caption("No playoff/final-style labels were available for the current filters.")
    else:
        st.dataframe(
            readable_table(
                pressure.head(15) if not chosen else pressure,
                ["team", "matches", "wins", "win_pct"],
                {"team": "Team", "matches": "Pressure matches", "wins": "Wins", "win_pct": "Win rate (%)"},
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Advanced Team Insights")
    advanced = team_advanced_insights(matches, deliveries)
    phase_table = team_phase_performance(deliveries)
    if chosen:
        advanced = selected_team_rows(advanced, teams)
        phase_table = selected_team_rows(phase_table, teams)
    st.plotly_chart(
        grouped_bar_chart(
            phase_table,
            "team",
            "run_rate",
            "phase",
            "Best phase performance by team",
            "Team",
            "Runs per over",
            height=520,
        ),
        use_container_width=True,
        config=chart_config("team_phase_performance"),
    )
    st.dataframe(
        readable_table(
            advanced.head(25) if not chosen else advanced,
            [
                "team",
                "matches",
                "win_pct",
                "home_advantage_score",
                "away_win_pct",
                "chasing_strength_score",
                "defending_strength_score",
                "team_consistency_index",
                "best_phase",
            ],
            {
                "team": "Team",
                "matches": "Matches",
                "win_pct": "Win %",
                "home_advantage_score": "Home advantage",
                "away_win_pct": "Away win %",
                "chasing_strength_score": "Chasing strength",
                "defending_strength_score": "Defending strength",
                "team_consistency_index": "Consistency index",
                "best_phase": "Best phase",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )
    csv_download("Download team insights CSV", advanced, "team_advanced_insights.csv")


def player_peak_career(deliveries: pd.DataFrame, player: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute selected player's career totals and season peaks."""
    if deliveries.empty or player == "All":
        return pd.DataFrame(), pd.DataFrame()

    batting = batting_leaderboard(deliveries, min_balls=0)
    bowling = bowling_leaderboard(deliveries, min_overs=0)
    impact = player_impact_scores(deliveries, min_balls=0)

    batting_row = batting[batting["batter"].eq(player)]
    bowling_row = bowling[bowling["bowler"].eq(player)]
    impact_row = impact[impact["batter"].eq(player)]

    career = pd.DataFrame(
        [
            {
                "player": player,
                "career_runs": int(batting_row["runs"].iloc[0]) if not batting_row.empty else 0,
                "balls_faced": int(batting_row["balls"].iloc[0]) if not batting_row.empty else 0,
                "batting_average": batting_row["batting_average"].iloc[0] if not batting_row.empty else pd.NA,
                "strike_rate": batting_row["strike_rate"].iloc[0] if not batting_row.empty else 0,
                "fours": int(batting_row["fours"].iloc[0]) if not batting_row.empty else 0,
                "sixes": int(batting_row["sixes"].iloc[0]) if not batting_row.empty else 0,
                "wickets": int(bowling_row["wickets"].iloc[0]) if not bowling_row.empty else 0,
                "economy": bowling_row["economy"].iloc[0] if not bowling_row.empty else pd.NA,
                "bowling_average": bowling_row["bowling_average"].iloc[0] if not bowling_row.empty else pd.NA,
                "impact_score": impact_row["impact_score"].iloc[0] if not impact_row.empty else 0,
            }
        ]
    )

    season_batting = pd.DataFrame()
    player_batting = deliveries[deliveries["batter"].eq(player)]
    if not player_batting.empty:
        season_batting = player_batting.groupby("season", as_index=False).agg(
            runs=("batter_runs", "sum"),
            balls=("legal_ball", "sum"),
            fours=("is_four", "sum"),
            sixes=("is_six", "sum"),
        )
        season_batting["strike_rate"] = season_batting.apply(
            lambda row: round(row["runs"] / row["balls"] * 100, 2) if row["balls"] else 0,
            axis=1,
        )

    season_bowling = pd.DataFrame()
    player_bowling = deliveries[deliveries["bowler"].eq(player)]
    if not player_bowling.empty:
        bowling_copy = player_bowling.copy()
        bowling_copy["bowler_wicket"] = (
            (bowling_copy["is_wicket"] == 1)
            & (~bowling_copy["wicket_kind"].str.lower().isin(NON_BOWLER_WICKET_KINDS))
        ).astype(int)
        season_bowling = bowling_copy.groupby("season", as_index=False).agg(
            wickets=("bowler_wicket", "sum"),
            balls_bowled=("legal_ball", "sum"),
            runs_conceded=("total_runs", "sum"),
        )
        season_bowling["economy"] = season_bowling.apply(
            lambda row: round(row["runs_conceded"] / row["balls_bowled"] * 6, 2) if row["balls_bowled"] else 0,
            axis=1,
        )

    if season_batting.empty:
        peak = season_bowling
    elif season_bowling.empty:
        peak = season_batting
    else:
        peak = season_batting.merge(season_bowling, on="season", how="outer")
    if not peak.empty:
        peak = peak.fillna(0)
        for column in ("runs", "wickets", "strike_rate"):
            if column not in peak:
                peak[column] = 0
        peak = peak.sort_values(["runs", "wickets", "strike_rate"], ascending=False)

    return career, peak


def player_match_drilldown(matches: pd.DataFrame, deliveries: pd.DataFrame, player: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return selected-player match, team, and venue summaries for current filters."""
    if matches.empty or deliveries.empty or player == "All":
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    player_matches = []
    for _, match in matches.iterrows():
        player_map = match.get("players", {})
        teams = []
        if isinstance(player_map, dict):
            teams = [team for team, names in player_map.items() if isinstance(names, list) and player in names]
        if teams:
            player_matches.append(
                {
                    "match_id": match["match_id"],
                    "date": match["date"],
                    "season": match["season"],
                    "team": teams[0],
                    "venue": match["venue"],
                    "winner": match["winner"],
                }
            )

    context = pd.DataFrame(player_matches)
    player_batting = deliveries[deliveries["batter"].eq(player)]
    player_bowling = deliveries[deliveries["bowler"].eq(player)].copy()

    if context.empty:
        batting_context = player_batting.groupby("match_id", as_index=False).agg(team=("batting_team", "first"))
        bowling_context = player_bowling.groupby("match_id", as_index=False).agg(team=("bowling_team", "first"))
        context = pd.concat([batting_context, bowling_context], ignore_index=True).drop_duplicates("match_id")
        context = context.merge(matches[["match_id", "date", "season", "venue", "winner"]], on="match_id", how="left")

    if context.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    batting = player_batting.groupby("match_id", as_index=False).agg(
        runs=("batter_runs", "sum"),
        balls=("legal_ball", "sum"),
        fours=("is_four", "sum"),
        sixes=("is_six", "sum"),
    )
    bowling = pd.DataFrame(columns=["match_id", "wickets", "balls_bowled", "runs_conceded"])
    if not player_bowling.empty:
        player_bowling["bowler_wicket"] = (
            (player_bowling["is_wicket"] == 1)
            & (~player_bowling["wicket_kind"].str.lower().isin(NON_BOWLER_WICKET_KINDS))
        ).astype(int)
        bowling = player_bowling.groupby("match_id", as_index=False).agg(
            wickets=("bowler_wicket", "sum"),
            balls_bowled=("legal_ball", "sum"),
            runs_conceded=("total_runs", "sum"),
        )

    match_summary = (
        context.merge(batting, on="match_id", how="left")
        .merge(bowling, on="match_id", how="left")
        .fillna({"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "wickets": 0, "balls_bowled": 0, "runs_conceded": 0})
    )
    match_summary["strike_rate"] = match_summary.apply(
        lambda row: round(row["runs"] / row["balls"] * 100, 2) if row["balls"] else 0,
        axis=1,
    )
    match_summary["economy"] = match_summary.apply(
        lambda row: round(row["runs_conceded"] / row["balls_bowled"] * 6, 2) if row["balls_bowled"] else 0,
        axis=1,
    )
    match_summary["result"] = match_summary.apply(lambda row: "Won" if row["team"] == row["winner"] else "Lost", axis=1)
    match_summary = match_summary.sort_values(["date", "match_id"])

    team_summary = match_summary.groupby("team", as_index=False).agg(
        matches=("match_id", "nunique"),
        runs=("runs", "sum"),
        wickets=("wickets", "sum"),
        wins=("result", lambda s: int((s == "Won").sum())),
    )
    team_summary["win_pct"] = team_summary["wins"].div(team_summary["matches"]).mul(100).round(2)

    venue_summary = match_summary.groupby("venue", as_index=False).agg(
        matches=("match_id", "nunique"),
        runs=("runs", "sum"),
        wickets=("wickets", "sum"),
        avg_runs=("runs", "mean"),
        highest_score=("runs", "max"),
    )
    venue_summary["avg_runs"] = venue_summary["avg_runs"].round(2)
    venue_summary = venue_summary.sort_values(["runs", "matches"], ascending=False)
    return match_summary, team_summary.sort_values(["runs", "matches"], ascending=False), venue_summary


def page_player_analytics(matches: pd.DataFrame, deliveries: pd.DataFrame, teams: list[str], selected_player: str = "All") -> None:
    """Render batting and bowling leaderboards."""
    st.title("Player Analytics")
    st.markdown(
        '<p class="small-note">Use the thresholds below to avoid noisy leaderboards from players with very few balls or overs.</p>',
        unsafe_allow_html=True,
    )
    min_balls = st.slider("Minimum batting balls", min_value=0, max_value=300, value=30, step=10)
    min_overs = st.slider("Minimum bowling overs", min_value=0, max_value=100, value=5, step=5)

    chosen = selected_values(teams)
    batting_input = deliveries
    bowling_input = deliveries
    if chosen:
        batting_input = deliveries[deliveries["batting_team"].isin(chosen)]
        bowling_input = deliveries[deliveries["bowling_team"].isin(chosen)]
        st.info(f"Showing batting and bowling records only for: {', '.join(chosen)}")

    batting = batting_leaderboard(batting_input, min_balls=min_balls)
    bowling = bowling_leaderboard(bowling_input, min_overs=float(min_overs))
    impact = player_impact_scores(batting_input, min_balls=max(60, min_balls))
    death_batters = phase_batting_leaderboard(batting_input, "Death Overs", min_balls=40)
    powerplay_batters = phase_batting_leaderboard(batting_input, "Powerplay", min_balls=40)
    death_bowlers = phase_bowling_leaderboard(bowling_input, "Death Overs", min_overs=5)
    if selected_player != "All":
        career, peaks = player_peak_career(deliveries, selected_player)
        match_summary, team_summary, venue_summary = player_match_drilldown(matches, deliveries, selected_player)
        if career.empty or (career["career_runs"].iloc[0] == 0 and career["wickets"].iloc[0] == 0):
            st.warning("No batting or bowling record is available for the selected player in the current filters.")
        else:
            row = career.iloc[0]
            st.subheader(f"{selected_player}: Peak Career Summary")
            cols = st.columns(5)
            cols[0].metric("Career runs", f"{int(row['career_runs']):,}")
            cols[1].metric("Strike rate", f"{float(row['strike_rate']):.2f}")
            cols[2].metric("Batting average", "N/A" if pd.isna(row["batting_average"]) else f"{float(row['batting_average']):.2f}")
            cols[3].metric("Wickets", f"{int(row['wickets']):,}")
            cols[4].metric("Impact score", f"{float(row['impact_score']):.2f}")
            st.dataframe(career, use_container_width=True, hide_index=True)
            if not peaks.empty:
                st.subheader("Season Peaks")
                st.dataframe(peaks.head(10), use_container_width=True, hide_index=True)
            if not team_summary.empty:
                st.subheader("Teams Played For")
                st.dataframe(team_summary, use_container_width=True, hide_index=True)
            if not venue_summary.empty:
                st.subheader("Where He Played")
                st.dataframe(venue_summary, use_container_width=True, hide_index=True)
            if not match_summary.empty:
                left, right = st.columns(2)
                with left:
                    st.plotly_chart(
                        line_chart(
                            match_summary,
                            "date",
                            "runs",
                            f"{selected_player} match-by-match batting peak",
                            "Match date",
                            "Runs",
                            color="team",
                            height=440,
                        ),
                        use_container_width=True,
                        key=f"player_match_peak_{selected_player}",
                    )
                with right:
                    st.plotly_chart(
                        horizontal_bar_chart(
                            venue_summary.sort_values("runs", ascending=False).head(10),
                            "venue",
                            "runs",
                            f"{selected_player} runs by venue",
                            "Runs",
                            height=440,
                        ),
                        use_container_width=True,
                        key=f"player_runs_by_venue_{selected_player}",
                    )
                st.subheader("Match Analytics")
                st.dataframe(
                    match_summary[
                        [
                            "date",
                            "season",
                            "team",
                            "venue",
                            "runs",
                            "balls",
                            "strike_rate",
                            "wickets",
                            "economy",
                            "result",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        batting = batting[batting["batter"].eq(selected_player)]
        bowling = bowling[bowling["bowler"].eq(selected_player)]
        impact = impact[impact["batter"].eq(selected_player)]

    tab_batting, tab_bowling, tab_impact, tab_phase = st.tabs(["Batting", "Bowling", "Impact Scores", "Phase Specialists"])
    with tab_batting:
        st.plotly_chart(
            horizontal_bar_chart(batting.head(15), "batter", "runs", "Top run scorers", "Runs", height=520),
            use_container_width=True,
            key=f"player_batting_chart_{selected_player}",
        )
        st.dataframe(
            readable_table(
                batting.head(50),
                ["batter", "runs", "balls", "dismissals", "batting_average", "strike_rate", "fours", "sixes", "boundary_pct", "consistency_index"],
                {
                    "batter": "Batter",
                    "runs": "Runs",
                    "balls": "Balls",
                    "dismissals": "Dismissals",
                    "batting_average": "Average",
                    "strike_rate": "Strike rate",
                    "fours": "4s",
                    "sixes": "6s",
                    "boundary_pct": "Boundary %",
                    "consistency_index": "Consistency index",
                },
            ),
            use_container_width=True,
            hide_index=True,
        )
        csv_download("Download batting CSV", batting, "batting_leaderboard.csv")
    with tab_bowling:
        st.plotly_chart(
            horizontal_bar_chart(bowling.head(15), "bowler", "wickets", "Top wicket takers", "Wickets", height=520),
            use_container_width=True,
            key=f"player_bowling_chart_{selected_player}",
        )
        st.dataframe(
            readable_table(
                bowling.head(50),
                ["bowler", "overs", "runs_conceded", "wickets", "economy", "bowling_average"],
                {
                    "bowler": "Bowler",
                    "overs": "Overs",
                    "runs_conceded": "Runs conceded",
                    "wickets": "Wickets",
                    "economy": "Economy",
                    "bowling_average": "Bowling average",
                },
            ),
            use_container_width=True,
            hide_index=True,
        )
        csv_download("Download bowling CSV", bowling, "bowling_leaderboard.csv")
    with tab_impact:
        st.plotly_chart(
            horizontal_bar_chart(impact.head(15), "batter", "impact_score", "Most valuable players by impact score", "Impact score", height=520),
            use_container_width=True,
            config=chart_config("player_impact_scores"),
            key=f"player_impact_chart_{selected_player}",
        )
        st.dataframe(
            readable_table(
                impact.head(50),
                ["batter", "runs", "strike_rate", "boundary_pct", "impact_score", "consistency_score", "pressure_performance_score"],
                {
                    "batter": "Player",
                    "runs": "Runs",
                    "strike_rate": "Strike rate",
                    "boundary_pct": "Boundary %",
                    "impact_score": "Impact score",
                    "consistency_score": "Consistency score",
                    "pressure_performance_score": "Pressure score",
                },
            ),
            use_container_width=True,
            hide_index=True,
        )
        csv_download("Download impact CSV", impact, "player_impact_scores.csv")
    with tab_phase:
        left, right = st.columns(2)
        with left:
            st.subheader("Best Death-Over Batsmen")
            st.dataframe(death_batters.head(20), use_container_width=True, hide_index=True)
            st.subheader("Best Powerplay Batsmen")
            st.dataframe(powerplay_batters.head(20), use_container_width=True, hide_index=True)
        with right:
            st.subheader("Best Death-Over Bowlers")
            st.dataframe(death_bowlers.head(20), use_container_width=True, hide_index=True)


def page_toss_analysis(matches: pd.DataFrame, deliveries: pd.DataFrame, teams: list[str]) -> None:
    """Render toss and innings outcome analysis."""
    if not page_intro(
        "Toss Analysis",
        "Understand whether toss decisions are associated with winning outcomes, and compare chasing with defending.",
        matches,
    ):
        return
    chosen = selected_values(teams)
    toss_matches = matches
    if chosen:
        toss_matches = matches[matches["toss_winner"].isin(chosen)]
        st.info(f"Toss charts focus on matches where {', '.join(chosen)} won the toss.")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            horizontal_bar_chart(
                toss_impact(toss_matches),
                "toss_decision",
                "toss_win_match_win_pct",
                "Toss winner match win rate",
                "Win rate (%)",
            ),
            use_container_width=True,
        )
    with right:
        outcome_data = selected_team_match_outcomes(matches, deliveries, teams)
        if outcome_data.empty:
            outcome_data = chase_vs_defend(matches, deliveries)
        st.plotly_chart(
            donut_chart(
                outcome_data,
                "result_type",
                "matches",
                "Selected team chasing/defending outcomes" if chosen else "Chasing versus defending wins",
            ),
            use_container_width=True,
        )

    venue_toss = toss_matches[(toss_matches["toss_winner"] != "Unknown") & (toss_matches["winner"] != "Unknown")].copy()
    if not venue_toss.empty:
        venue_toss["toss_winner_won"] = venue_toss["toss_winner"] == venue_toss["winner"]
        trend = venue_toss.groupby(["venue", "toss_decision"], as_index=False).agg(
            matches=("match_id", "count"),
            success_rate=("toss_winner_won", "mean"),
        )
        trend["success_rate"] = (trend["success_rate"] * 100).round(2)
        st.plotly_chart(
            horizontal_bar_chart(
                trend.sort_values("matches", ascending=False).head(30),
                "venue",
                "success_rate",
                "Venue-specific toss trends",
                "Toss winner win rate (%)",
                color="toss_decision",
                height=620,
            ),
            use_container_width=True,
        )


def page_venue_analytics(matches: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """Render venue analytics page."""
    if not page_intro(
        "Venue Analytics",
        "Review scoring conditions by venue, including first-innings scoring and how often chasing succeeds.",
        matches,
    ):
        return
    venues = venue_trends(matches, deliveries)
    advanced = venue_advanced_insights(matches, deliveries)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            horizontal_bar_chart(
                venues.head(15),
                "venue",
                "avg_first_innings_score",
                "Average first-innings score",
                "Runs",
                height=560,
            ),
            use_container_width=True,
        )
    with right:
        st.plotly_chart(
            horizontal_bar_chart(
                venues.head(15),
                "venue",
                "chase_success_rate",
                "Chase success rate",
                "Success rate (%)",
                height=560,
            ),
            use_container_width=True,
        )

    innings_scores = deliveries.groupby(["match_id", "innings_number"], as_index=False).agg(score=("total_runs", "sum"))
    st.plotly_chart(histogram(innings_scores, "score", "Innings score distribution", "Runs in innings"), use_container_width=True)
    st.dataframe(
        readable_table(
            venues,
            ["venue", "matches", "avg_first_innings_score", "chase_success_rate", "highest_successful_chase"],
            {
                "venue": "Venue",
                "matches": "Matches",
                "avg_first_innings_score": "Avg 1st innings score",
                "chase_success_rate": "Chase success %",
                "highest_successful_chase": "Highest successful chase",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Advanced Venue Bias")
    st.dataframe(
        readable_table(
            advanced,
            [
                "venue",
                "matches",
                "batting_friendly_index",
                "bowling_friendly_index",
                "avg_first_innings_score",
                "avg_second_innings_score",
                "toss_influence_pct",
                "chasing_success_pct",
                "venue_bias_score",
            ],
            {
                "venue": "Venue",
                "matches": "Matches",
                "batting_friendly_index": "Batting friendly index",
                "bowling_friendly_index": "Bowling friendly index",
                "avg_first_innings_score": "Avg 1st innings",
                "avg_second_innings_score": "Avg 2nd innings",
                "toss_influence_pct": "Toss influence %",
                "chasing_success_pct": "Chasing success %",
                "venue_bias_score": "Venue bias score",
            },
        ),
        use_container_width=True,
        hide_index=True,
    )
    csv_download("Download venue insights CSV", advanced, "venue_advanced_insights.csv")


def page_data_quality(report: pd.DataFrame) -> None:
    """Render data quality report page."""
    st.title("Data Quality Dashboard")
    st.markdown(
        '<p class="small-note">Every raw JSON file is validated independently. Invalid matches are skipped, logged, and do not stop the dashboard pipeline.</p>',
        unsafe_allow_html=True,
    )
    values = dict(zip(report["metric"], report["value"])) if not report.empty else {}
    columns = st.columns(4)
    for column, metric in zip(columns, ["Total files processed", "Valid files", "Files rejected", "Records skipped"]):
        column.metric(metric, values.get(metric, "0"))
    score_columns = st.columns(4)
    for column, metric in zip(score_columns, ["Missing fields", "Duplicates removed", "Schema violations", "Quality Status"]):
        column.metric(metric, values.get(metric, "0"))
    st.metric("Data Quality Percentage", values.get("Data Quality Percentage", "0.00%"))
    st.dataframe(report, use_container_width=True, hide_index=True)
    csv_download("Download data quality CSV", report, "data_quality_report.csv")
    st.caption("Detailed validation events are written to logs/data_quality.log.")


def page_ai_insights(matches: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """Render automated insight panel."""
    if not page_intro(
        "AI Generated Insights",
        "Automated analyst notes generated from the currently filtered dataset. The text is computed from statistics, not hardcoded claims.",
        matches,
    ):
        return
    insights = generate_ai_insights(matches, deliveries)
    for insight in insights:
        st.markdown(f'<div class="section-note">{insight}</div>', unsafe_allow_html=True)


def page_ai_query(matches: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """Render deterministic natural-language query assistant."""
    st.title("Ask IPL AI")
    st.markdown(
        '<p class="small-note">Ask a cricket analytics question. The assistant routes the query to deterministic Pandas analytics and returns only dataset-grounded results.</p>',
        unsafe_allow_html=True,
    )
    examples = [
        "Who is the best death over bowler?",
        "Which team dominates at Wankhede?",
        "Does winning the toss matter?",
        "Compare Chennai Super Kings and Mumbai Indians after 2020.",
        "Who has highest strike rate among players with 1000+ runs?",
    ]
    query = st.text_input("AI Query Assistant", value=examples[0])
    selected_example = st.selectbox("Try an example", examples)
    if st.button("Use example"):
        query = selected_example
    if query:
        result = route_query(query, matches, deliveries)
        st.subheader("Verified Result")
        if result.verification_badge == "Verified Dataset Result":
            st.success(result.answer)
        elif result.verification_badge == "Partially Supported":
            st.warning(result.answer)
        else:
            st.error(result.answer)
        st.markdown(f"**Verification Badge:** {result.verification_badge}")
        st.markdown(f"**Detected Intent:** {result.intent}")
        st.markdown(f"**Applied Filters:** {result.applied_filters or 'None'}")
        st.markdown(f"**Metrics Used:** {', '.join(result.metrics_used) or 'None'}")
        st.markdown(f"**Records Analysed:** {result.records_analysed}")
        st.markdown(f"**Query Execution Method:** {result.execution_method}")
        st.markdown(f"**Source:** {result.source}")
        st.markdown(f"**Validation:** {result.validation}")
        if not result.data.empty:
            st.dataframe(result.data, use_container_width=True, hide_index=True)
            csv_download("Download query result CSV", result.data, "ipl_ai_query_result.csv")


def page_architecture() -> None:
    """Render architecture and reproducibility notes."""
    st.title("Architecture")
    st.markdown(
        """
```mermaid
flowchart TD
    A["Cricsheet IPL JSON"] --> B["Data Quality Validation"]
    B --> C["Fault-Tolerant Loader"]
    C --> D["JSON Transformer"]
    D --> E["Clean Match and Delivery Tables"]
    E --> F["Analytics Engine"]
    F --> G["Streamlit Dashboard"]
    F --> H["AI Insight Generator"]
    F --> I["Query Router"]
    I --> J["Verified Dataset Result"]
```
        """
    )
    st.subheader("Execution Contract")
    st.write("All metrics are computed from loaded match and delivery DataFrames. The AI assistant never generates cricket facts directly; it routes natural language to deterministic analytics functions.")
    st.subheader("Reproducibility")
    st.write("Run `python -m unittest discover tests` to validate win rates, toss analysis, venue metrics, impact scores, query routing, and data validation on deterministic fixtures.")


def page_query_demo(matches: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """Render one-click query verification demos."""
    st.title("Query Verification Demo")
    queries = [
        "Who is the best death over bowler?",
        "Does winning the toss matter?",
        "Which venue favors chasing?",
        "Compare CSK and MI after 2020.",
        "Most impactful batsman.",
    ]
    selected = st.radio("One-click execution", queries)
    if st.button("Run verified query"):
        result = route_query(selected, matches, deliveries)
        st.subheader(result.verification_badge)
        st.write(result.answer)
        st.dataframe(
            pd.DataFrame(
                [
                    {"Field": "Intent", "Value": result.intent},
                    {"Field": "Filters", "Value": result.applied_filters or "None"},
                    {"Field": "Metrics", "Value": ", ".join(result.metrics_used) or "None"},
                    {"Field": "Records Analysed", "Value": result.records_analysed},
                    {"Field": "Method", "Value": result.execution_method},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        if not result.data.empty:
            st.dataframe(result.data, use_container_width=True, hide_index=True)


def main() -> None:
    """Run the dashboard application."""
    ensure_directories()

    st.sidebar.title("Navigation")
    dark_mode = st.sidebar.toggle("Dark mode", value=False)
    _inject_style(dark_mode)
    page = st.sidebar.radio(
        "Page",
        [
            "Overview",
            "Team Analytics",
            "Player Analytics",
            "Toss Analysis",
            "Venue Analytics",
            "AI Insights",
            "Ask IPL AI",
            "Query Demo",
        ],
        label_visibility="collapsed",
    )

    matches, deliveries = load_data(str(RAW_DATA_DIR))
    if matches.empty or deliveries.empty:
        show_data_instructions()
        return

    seasons, teams, selected_player = sidebar_filters(matches)
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Selected season: {selected_label(seasons)}")
    st.sidebar.caption(f"Selected team: {selected_label(teams)}")
    st.sidebar.caption(f"Selected player: {selected_player}")
    filtered_matches = filter_by_team_matches(filter_by_season(matches, seasons), teams)
    valid_match_ids = set(filtered_matches["match_id"])
    filtered_deliveries = filter_by_season(deliveries[deliveries["match_id"].isin(valid_match_ids)], seasons)

    if page == "Overview":
        page_overview(filtered_matches, filtered_deliveries, teams)
    elif page == "Team Analytics":
        page_team_analytics(filtered_matches, filtered_deliveries, teams)
    elif page == "Player Analytics":
        page_player_analytics(filtered_matches, filtered_deliveries, teams, selected_player)
    elif page == "Toss Analysis":
        page_toss_analysis(filtered_matches, filtered_deliveries, teams)
    elif page == "Venue Analytics":
        page_venue_analytics(filtered_matches, filtered_deliveries)
    elif page == "AI Insights":
        page_ai_insights(filtered_matches, filtered_deliveries)
    elif page == "Ask IPL AI":
        page_ai_query(filtered_matches, filtered_deliveries)
    elif page == "Query Demo":
        page_query_demo(filtered_matches, filtered_deliveries)
    else:
        page_query_demo(filtered_matches, filtered_deliveries)


if __name__ == "__main__":
    main()
