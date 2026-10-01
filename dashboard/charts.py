"""Read-only Plotly views for the trading desk."""
from __future__ import annotations

from math import isfinite

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import settings

SURFACE = "#111a23"
TEXT = "#e8edf2"
GRID = "#263440"
UP = "#58dcc0"
DOWN = "#ff8494"
GOLD = "#dfc178"


def _style(figure: go.Figure, height: int) -> go.Figure:
    figure.update_layout(
        template="plotly_dark", height=height, paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE, font={"family": "Arial, sans-serif", "color": TEXT, "size": 12},
        margin={"l": 12, "r": 22, "t": 32, "b": 28},
        legend={"orientation": "h", "x": 0, "y": 1.1, "font": {"size": 11}},
        hoverlabel={"bgcolor": GRID, "font_size": 12},
    )
    figure.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, showgrid=False, automargin=True)
    figure.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, automargin=True)
    return figure


def _plan_levels(plan) -> tuple[float, ...] | None:
    """Do not draw actionable levels for an incomplete or invalid trade plan."""
    try:
        signal = plan.signal.value
        if signal not in {"BUY", "STRONG BUY", "SELL", "STRONG SELL"}:
            return None
        low, high = plan.entry_zone
        levels = tuple(float(value) for value in (low, high, plan.stop_loss, plan.tp1, plan.tp2, plan.tp3))
        low, high, stop, tp1, tp2, tp3 = levels
        valid = all(isfinite(value) and value > 0 for value in levels) and low <= high
        valid = valid and (stop < low <= high < tp1 <= tp2 <= tp3 if signal.endswith("BUY") else tp3 <= tp2 <= tp1 < low <= high < stop)
        return levels if valid else None
    except (AttributeError, TypeError, ValueError):
        return None


def price_chart(result: dict, chart_type: str = "Candles", show_ema: bool = True,
                show_zones: bool = True, timeframe: str = "") -> go.Figure:
    """Price and volume; chart coordinates are Bangkok wall time, labeled UTC+7."""
    frame = result["candles"].tail(500)
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.8, .2], vertical_spacing=.04)
    if frame.empty:
        figure.add_annotation(text="No candles available", x=.5, y=.5, xref="paper", yref="paper", showarrow=False)
        return _style(figure, 420)
    times = pd.to_datetime(frame.time, utc=True).dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
    if chart_type == "Candles":
        figure.add_trace(go.Candlestick(
            x=times, open=frame.open, high=frame.high, low=frame.low, close=frame.close,
            name="Price", increasing={"line_color": UP, "fillcolor": SURFACE},
            decreasing={"line_color": DOWN, "fillcolor": DOWN},
        ), row=1, col=1)
    else:
        figure.add_trace(go.Scatter(x=times, y=frame.close, name="Close", mode="lines", line={"color": GOLD, "width": 2}), row=1, col=1)
    if show_ema:
        for name, color in (("ema20", GOLD), ("ema50", "#83b5f5"), ("ema200", "#b5a8ed")):
            if name in frame:
                figure.add_trace(go.Scatter(x=times, y=frame[name], name=name.upper(), mode="lines", line={"color": color, "width": 1}), row=1, col=1)
    volume = frame.get("volume", frame.get("tick_volume", pd.Series(0, index=frame.index)))
    figure.add_trace(go.Bar(
        x=times, y=volume, name="Volume", showlegend=False, opacity=.5,
        marker_color=[UP if close >= open_ else DOWN for open_, close in zip(frame.open, frame.close)],
        hovertemplate="%{x|%d %b %H:%M} UTC+7<br>Volume %{y:,.0f}<extra></extra>",
    ), row=2, col=1)
    if show_zones:
        for key, label, color in (("nearest_support", "Support", UP), ("nearest_resistance", "Resistance", DOWN)):
            zone = result.get("levels", {}).get(key)
            if zone is not None and isfinite(zone.low) and isfinite(zone.high) and 0 < zone.low <= zone.high:
                figure.add_hrect(y0=zone.low, y1=zone.high, fillcolor=color, opacity=.1,
                                 line_width=0, layer="below", row=1, col=1)
                figure.add_annotation(x=0, xref="x domain", y=zone.high, yref="y", text=label,
                                      xanchor="left", yanchor="bottom", showarrow=False, font={"color": color, "size": 11})
    plan = result.get("plan")
    levels = _plan_levels(plan)
    if levels:
        low, high, stop, tp1, tp2, tp3 = levels
        figure.add_hrect(y0=low, y1=high, fillcolor=GOLD, opacity=.12, line_width=0, layer="below", row=1, col=1)
        figure.add_annotation(x=1, xref="x domain", y=(low + high) / 2, yref="y", text="Entry",
                              xanchor="right", yanchor="bottom", showarrow=False, font={"color": GOLD, "size": 11})
        for label, value, color in (("SL", stop, DOWN), ("TP1", tp1, UP), ("TP2", tp2, UP), ("TP3", tp3, UP)):
            figure.add_hline(y=value, line_color=color, line_dash="dot", line_width=1,
                             annotation_text=label, annotation_font_color=color, annotation_font_size=11, row=1, col=1)
    figure.update_layout(hovermode="x unified", uirevision=f"{getattr(plan, 'symbol', '')}:{timeframe}")
    figure.update_xaxes(rangeslider_visible=False, tickformat="%d %b\n%H:%M", hoverformat="%d %b %Y %H:%M UTC+7")
    figure.update_xaxes(title_text="Bangkok · UTC+7", row=2, col=1)
    figure.update_yaxes(side="right", tickformat=",.2f", row=1, col=1)
    figure.update_yaxes(title_text="Vol.", nticks=3, tickformat="~s", row=2, col=1)
    return _style(figure, 420)


def signal_chart(components: dict[str, float]) -> go.Figure:
    """Show signed contributions to the strategy score, not probabilities."""
    names = list(settings.signal_weights)
    values = [max(-1, min(1, components.get(name, 0))) * settings.signal_weights[name] * 100 for name in names]
    labels = [name.replace("_", " ").title() for name in names]
    figure = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color=[UP if value >= 0 else DOWN for value in values],
        text=[f"{value:+.1f}" for value in values], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:+.2f} score points<extra></extra>",
    ))
    figure.update_layout(showlegend=False, margin={"l": 12, "r": 28, "t": 8, "b": 20})
    figure.update_xaxes(title_text="Sell ← score points → Buy", range=[-25, 25], dtick=10)
    figure.update_yaxes(autorange="reversed")
    return _style(figure, 310)


def pnl_chart(frame: pd.DataFrame) -> go.Figure:
    """Net realized P/L supplied by the snapshot, without fabricating equity."""
    figure = go.Figure()
    if not frame.empty:
        times = pd.to_datetime(frame.time, utc=True).dt.tz_convert("Asia/Bangkok").dt.tz_localize(None)
        figure.add_trace(go.Scatter(
            x=times, y=frame.cumulative_pnl, customdata=frame.realized_pnl,
            name="Net realized P/L", mode="lines+markers", fill="tozeroy",
            line={"color": GOLD, "width": 2}, marker={"size": 5}, fillcolor="rgba(223,193,120,.10)",
            hovertemplate="%{x|%d %b %Y} · Bangkok<br>Daily net: %{customdata:+,.2f}<br>Cumulative net: %{y:+,.2f}<extra></extra>",
        ))
    figure.update_layout(showlegend=False, hovermode="x unified")
    figure.update_xaxes(tickformat="%d %b", title_text="Bangkok · UTC+7")
    figure.update_yaxes(title_text="Net realized P/L", tickformat=",.2f")
    return _style(figure, 250)
