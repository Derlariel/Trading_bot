"""Streamlit dashboard for MT5 analysis and stored performance."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from database.database import Database  # noqa: E402
from mt5.connector import MT5Connector  # noqa: E402
from mt5.market_data import MarketData  # noqa: E402
from risk.position_size import calculate_position_size  # noqa: E402
from strategy.strategy import analyze  # noqa: E402

st.set_page_config(page_title="Trading Bot", layout="wide")
st.markdown("""
<style>
:root {color-scheme: dark} .stApp {background:#020617;color:#f8fafc}
[data-testid="stMetric"] {background:#0e1223;border:1px solid #334155;border-radius:10px;padding:12px}
h1,h2,h3 {font-family:'Fira Sans',sans-serif} code,[data-testid="stMetricValue"] {font-family:'Fira Code',monospace}
.mode {display:inline-block;padding:5px 10px;border-radius:999px;background:#1e293b;color:#22c55e;border:1px solid #334155}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def resources() -> tuple[Database, MT5Connector]:
    database, connector = Database(), MT5Connector()
    connector.initialize()
    return database, connector


@st.cache_data(ttl=30)
def candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    return MarketData(resources()[1]).get_candles(symbol, timeframe, count)


def chart(result: dict[str, object]) -> go.Figure:
    frame: pd.DataFrame = result["candles"]  # type: ignore[assignment]
    figure = go.Figure(go.Candlestick(x=frame.time, open=frame.open, high=frame.high, low=frame.low, close=frame.close, name="Price"))
    for name, color in (("ema20", "#22c55e"), ("ema50", "#38bdf8"), ("ema200", "#a78bfa")):
        figure.add_scatter(x=frame.time, y=frame[name], name=name.upper(), line={"color": color, "width": 1})
    colors = {"support": "rgba(34,197,94,.16)", "resistance": "rgba(239,68,68,.16)"}
    for zone in result["zones"]:  # type: ignore[union-attr]
        figure.add_hrect(y0=zone.low, y1=zone.high, fillcolor=colors[zone.type], line_width=0, annotation_text=f"{zone.type.title()} {zone.strength:.0f}%")
    for label, key, color in (("BUY ZONE", "buy_zone", "#22c55e"), ("SELL ZONE", "sell_zone", "#ef4444")):
        zone = result[key]
        if zone:
            figure.add_annotation(x=frame.time.iloc[-1], y=(zone["low"] + zone["high"]) / 2, text=label, font={"color": color}, showarrow=False, xanchor="right")
    plan = result["plan"]
    for label, value, color in (("Entry", sum(plan.entry_zone) / 2, "#f8fafc"), ("SL", plan.stop_loss, "#ef4444"), ("TP1", plan.tp1, "#22c55e"), ("TP2", plan.tp2, "#14b8a6"), ("TP3", plan.tp3, "#38bdf8")):
        figure.add_hline(y=value, line_color=color, line_dash="dot", annotation_text=label)
    figure.update_layout(height=620, template="plotly_dark", paper_bgcolor="#020617", plot_bgcolor="#0e1223", xaxis_rangeslider_visible=False, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10))
    return figure


database, connector = resources()
st.title("AI-Assisted Trading Bot")
st.markdown(f'<span class="mode">{"DEMO / ANALYSIS" if not settings.live_trading else "LIVE"}</span>', unsafe_allow_html=True)
symbol = st.sidebar.selectbox("Symbol", settings.symbols)
timeframe = st.sidebar.selectbox("Timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], index=2)
uploaded = st.sidebar.file_uploader("หรืออัปโหลด OHLC CSV", type="csv")

try:
    data = pd.read_csv(uploaded) if uploaded else candles(symbol, timeframe, settings.candle_count)
    if "time" in data: data["time"] = pd.to_datetime(data["time"], utc=True)
    result, plan = analyze(symbol, data), None
    plan = result["plan"]
    tabs = st.tabs(["Overview", "Market Analyzer", "Signals", "News", "Performance"])
    with tabs[0]:
        account = connector.account_summary()
        trade_rows = database.rows("trades")
        today = pd.Timestamp.now(tz="UTC").date()
        daily_pnl = sum(float(row.get("pnl", 0)) for row in trade_rows if pd.to_datetime(row["created_at"], utc=True).date() == today)
        cols = st.columns(6)
        for column, (label, value) in zip(cols, (("Balance", account.get("balance", 0)), ("Equity", account.get("equity", 0)), ("Daily P&L", daily_pnl), ("Current", float(data.close.iloc[-1])), ("Open positions", len(connector.positions())), ("Confidence", plan.confidence))):
            column.metric(label, f"{value:,.2f}")
        st.json({"trend": result["trend"], "volume": result["volume"], "bot_status": "LIVE" if settings.live_trading else "ANALYSIS / DEMO MODE"})
    with tabs[1]:
        st.plotly_chart(chart(result), width="stretch")
    with tabs[2]:
        st.subheader(f"{plan.signal.value} · {plan.confidence:.1f}%")
        st.dataframe(pd.DataFrame([plan.to_dict()]), width="stretch", hide_index=True)
        spec, lot = connector.symbol_info(symbol), 0.0
        if account.get("balance") and spec and plan.stop_loss != sum(plan.entry_zone) / 2:
            try:
                lot = calculate_position_size(account["balance"], settings.risk_per_trade, sum(plan.entry_zone) / 2, plan.stop_loss, float(spec["trade_tick_size"]), float(spec["trade_tick_value"]), float(spec["volume_step"]), float(spec["volume_min"]), float(spec["volume_max"]))
            except (KeyError, ValueError):
                lot = 0.0
        st.metric("Suggested position size", f"{lot:g} lots" if lot else "Unavailable / no trade")
        st.json({"buy_zone": result["buy_zone"], "sell_zone": result["sell_zone"], "components": result["components"]})
    with tabs[3]:
        rows = database.rows("news")
        st.dataframe(pd.DataFrame(rows) if rows else pd.DataFrame(columns=["headline", "source", "published_at", "sentiment", "importance"]), width="stretch", hide_index=True)
    with tabs[4]:
        trades = pd.DataFrame(database.rows("trades"))
        if trades.empty: st.info("ยังไม่มี paper/live trade ที่ปิดแล้ว")
        else:
            cols = st.columns(4)
            cols[0].metric("Trades", len(trades)); cols[1].metric("Total P&L", f"{trades.pnl.sum():,.2f}")
            cols[2].metric("Win rate", f"{(trades.pnl.gt(0).mean()*100):.1f}%"); cols[3].metric("Open", int(trades.status.ne("CLOSED").sum()))
            st.dataframe(trades, width="stretch", hide_index=True)
except (ConnectionError, ValueError, KeyError) as error:
    st.error(f"โหลดข้อมูลไม่ได้: {error}")
    st.info("เปิด MT5 terminal และตรวจ symbol หรืออัปโหลด CSV ที่มี time/open/high/low/close/tick_volume")
