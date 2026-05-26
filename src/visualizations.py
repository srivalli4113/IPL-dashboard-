"""Accessible Plotly visualization helpers used by the Streamlit dashboard."""

from __future__ import annotations

import textwrap

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

TEMPLATE = "plotly_white"
PRIMARY_COLOR = "#0f766e"
SECONDARY_COLOR = "#2563eb"
ACCENT_COLOR = "#d97706"
GRID_COLOR = "#e5e7eb"
TEXT_COLOR = "#111827"
PALETTE = [
    "#0f766e",
    "#2563eb",
    "#d97706",
    "#7c3aed",
    "#be123c",
    "#047857",
    "#4338ca",
    "#a16207",
]


def _wrap_label(value: object, width: int = 22) -> str:
    """Wrap long labels so charts stay readable."""
    return "<br>".join(textwrap.wrap(str(value), width=width)) or str(value)


def _prepare_labels(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Add wrapped display labels without mutating the caller's dataframe."""
    prepared = df.copy()
    prepared[f"{column}_label"] = prepared[column].map(_wrap_label)
    return prepared


def _apply_common_layout(fig: go.Figure, title: str, height: int = 420) -> go.Figure:
    """Apply a consistent, high-contrast layout."""
    fig.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left", "font": {"size": 21}},
        template=TEMPLATE,
        height=height,
        margin={"l": 20, "r": 24, "t": 72, "b": 40},
        font={"family": "Arial, sans-serif", "size": 14, "color": TEXT_COLOR},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend_title_text="",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    fig.update_xaxes(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, title_font={"size": 15})
    fig.update_yaxes(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, title_font={"size": 15})
    return fig


def empty_figure(message: str = "No data available for the current filters") -> go.Figure:
    """Return a friendly empty-state figure."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 17, "color": TEXT_COLOR},
    )
    fig.update_layout(
        template=TEMPLATE,
        height=320,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig


def horizontal_bar_chart(
    df: pd.DataFrame,
    label: str,
    value: str,
    title: str,
    value_label: str,
    color: str | None = None,
    height: int = 460,
) -> go.Figure:
    """Create a horizontal bar chart for long names."""
    if df.empty or label not in df or value not in df:
        return empty_figure()

    prepared = _prepare_labels(df.sort_values(value, ascending=True), label)
    fig = px.bar(
        prepared,
        x=value,
        y=f"{label}_label",
        color=color,
        orientation="h",
        text=value,
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title=value_label)
    fig.update_yaxes(title="", automargin=True)
    return _apply_common_layout(fig, title, height=height)


def grouped_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    title: str,
    x_label: str,
    y_label: str,
    height: int = 440,
) -> go.Figure:
    """Create a grouped bar chart for filtered comparisons."""
    if df.empty or x not in df or y not in df or color not in df:
        return empty_figure()
    prepared = _prepare_labels(df, x)
    fig = px.bar(
        prepared,
        x=f"{x}_label",
        y=y,
        color=color,
        barmode="group",
        text=y,
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside", cliponaxis=False)
    fig.update_xaxes(title=x_label)
    fig.update_yaxes(title=y_label)
    return _apply_common_layout(fig, title, height=height)


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    x_label: str,
    y_label: str,
    color: str | None = None,
    height: int = 440,
) -> go.Figure:
    """Create an accessible line chart with markers."""
    if df.empty or x not in df or y not in df:
        return empty_figure()
    fig = px.line(
        df,
        x=x,
        y=y,
        color=color,
        markers=True,
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(line={"width": 3}, marker={"size": 8})
    fig.update_xaxes(title=x_label)
    fig.update_yaxes(title=y_label)
    return _apply_common_layout(fig, title, height=height)


def heatmap_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    value: str,
    title: str,
    x_label: str,
    y_label: str,
    height: int = 560,
) -> go.Figure:
    """Create a readable heatmap for season/team comparisons."""
    if df.empty or x not in df or y not in df or value not in df:
        return empty_figure()

    pivot = df.pivot_table(index=y, columns=x, values=value, aggfunc="mean")
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale=["#f8fafc", "#99f6e4", PRIMARY_COLOR],
        labels={"x": x_label, "y": y_label, "color": "Win rate (%)"},
        text_auto=".0f",
    )
    fig.update_xaxes(side="bottom", tickangle=0)
    fig.update_yaxes(automargin=True)
    return _apply_common_layout(fig, title, height=height)


def donut_chart(df: pd.DataFrame, names: str, values: str, title: str, height: int = 420) -> go.Figure:
    """Create a readable donut chart."""
    if df.empty or names not in df or values not in df:
        return empty_figure()
    fig = px.pie(
        df,
        names=names,
        values=values,
        hole=0.55,
        color_discrete_sequence=[PRIMARY_COLOR, ACCENT_COLOR, SECONDARY_COLOR],
    )
    fig.update_traces(textinfo="label+percent", textposition="outside")
    return _apply_common_layout(fig, title, height=height)


def histogram(df: pd.DataFrame, x: str, title: str, x_label: str, height: int = 420) -> go.Figure:
    """Create a scoring distribution histogram."""
    if df.empty or x not in df:
        return empty_figure()
    fig = px.histogram(df, x=x, nbins=25, color_discrete_sequence=[PRIMARY_COLOR])
    fig.update_xaxes(title=x_label)
    fig.update_yaxes(title="Number of innings")
    return _apply_common_layout(fig, title, height=height)
