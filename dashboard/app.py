"""Local trading desk: read-only analytics and an explicit Demo-only controller."""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from dashboard.charts import pnl_chart, price_chart, signal_chart  # noqa: E402
from dashboard.control import load_status, set_mode, start_worker, stop_worker  # noqa: E402
from dashboard.data import csv_bytes, load_account_snapshot  # noqa: E402
from database.database import Database  # noqa: E402
from mt5.connector import MT5Connector  # noqa: E402
from mt5.market_data import MarketData  # noqa: E402
from strategy.strategy import analyze  # noqa: E402

st.set_page_config(page_title="Aurum · Trading control", page_icon="◈", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_resource
def resources():
    database, connector = Database(), MT5Connector()
    connector.initialize()
    return database, connector


@st.cache_data(ttl=10, show_spinner=False)
def market_preview(symbol, timeframe):
    return analyze(symbol, MarketData(resources()[1]).get_candles(symbol, timeframe, settings.candle_count))


def markup(value):
    st.markdown(value, unsafe_allow_html=True)


def badge(label, color="gray"):
    return f'<span class="badge {color}">{escape(str(label))}</span>'


def empty(title, detail):
    markup(f'<div class="empty"><strong>{escape(title)}</strong><span>{escape(detail)}</span></div>')


def number(value, decimals=2):
    return "—" if value is None or pd.isna(value) else f"{value:,.{decimals}f}"


def timestamp(value):
    date = pd.to_datetime(value, utc=True, errors="coerce")
    return "—" if pd.isna(date) else date.tz_convert("Asia/Bangkok").strftime("%d %b %H:%M:%S")


def rules(items):
    markup(''.join(f'<div class="rule-row"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>' for label, value in items))


def latest_signal(database, symbol):
    for row in database.rows("signals", limit=500):
        if row["symbol"] != symbol:
            continue
        try:
            payload = json.loads(row["payload"])
            if isinstance(payload, dict):
                return {**payload, "saved_at": row["created_at"]}
        except (TypeError, ValueError):
            continue
    return {}


def controller(database, connector, status, snapshot):
    st.subheader("Execution controller")
    st.caption(f"Worker: {settings.symbols[0]} · {settings.timeframe} · ทุก 60 วินาที • การเลือกกราฟไม่เปลี่ยน symbol ของ Bot")
    cols = st.columns(3)
    if cols[0].button("Start analysis", type="primary", disabled=status["running"], width="stretch"):
        try:
            start_worker(database)
            st.session_state["control_notice"] = "เริ่ม Worker ในโหมด Manual แล้ว — ยังไม่อนุญาตให้เปิดออเดอร์"
            st.rerun()
        except Exception as error:
            st.error(f"เริ่ม Worker ไม่สำเร็จ: {error}")
    if cols[1].button("Manual / block entries", width="stretch", help="หยุดการเข้าออเดอร์ใหม่ แต่ให้ระบบวิเคราะห์ต่อ"):
        set_mode(database, "MANUAL", connector)
        st.rerun()
    if cols[2].button("Stop worker", disabled=not status["running"], width="stretch"):
        stop_worker(database)
        st.rerun()
    labels = {"MANUAL": "Manual — วิเคราะห์เท่านั้น", "AUTO_DEMO": "Auto Demo — เปิดออเดอร์เดโม่", "PAUSED": "Paused — พักการวิเคราะห์และออเดอร์"}
    with st.form("execution_mode"):
        target = st.radio("Execution mode", list(labels), index=list(labels).index(status["mode"]), format_func=labels.get)
        acknowledge = st.checkbox("ฉันยืนยันให้ Bot เปิดออเดอร์ในบัญชี Demo ตาม risk settings และ SL/TP ของสัญญาณ")
        apply = st.form_submit_button("Apply mode", width="stretch")
    if apply:
        if target == "AUTO_DEMO" and not acknowledge:
            st.warning("กรุณายืนยันการเปิดออเดอร์เดโม่ก่อนเปิด Auto Demo")
        elif target == "AUTO_DEMO" and (not snapshot["is_demo"] or not status["running"] or status["stop_requested"]):
            st.error("ต้องเชื่อมต่อบัญชี Demo และ Start analysis ให้ Worker ทำงานก่อน")
        else:
            try:
                set_mode(database, target, connector)
                st.session_state["control_notice"] = f"เปลี่ยนเป็น {target} แล้ว"
                st.rerun()
            except (ConnectionError, ValueError) as error:
                st.error(str(error))
    st.caption("Manual / Pause / Stop ไม่ปิด position เดิมและไม่ลบ SL/TP • คำสั่งที่ส่งถึงโบรกเกอร์แล้วอาจยังถูก fill • เทรดมือใน MT5")


def flow(status, snapshot, plan):
    execution = status["last_execution"]
    nodes = [
        ("MT5 feed", "Connected" if snapshot["connected"] else "Disconnected", "active" if snapshot["connected"] else "blocked"),
        ("Analysis", status["phase"] if status["running"] else "Worker offline", "active" if status["running"] and status["phase"] == "ANALYZING" else ""),
        ("Signal", plan.get("signal", "Awaiting analysis"), "active" if plan else ""),
        ("Risk checks", execution.get("reason", "Pending evaluation"), "blocked" if execution.get("decision") == "SKIP" else ""),
        ("Execution", f'{status["mode"]} · {status["state"]}', "active" if status["running"] and status["mode"] == "AUTO_DEMO" and snapshot["is_demo"] else ""),
    ]
    markup('<div class="eyebrow">System flow · สถานะล่าสุด ไม่ใช่การรับรองว่าจะเข้าออเดอร์</div><div class="flow">' + ''.join(
        f'<div class="flow-node {style}"><div class="flow-index">0{i}</div><div class="flow-title">{escape(title)}</div><div class="flow-state">{escape(str(detail))}</div></div>'
        for i, (title, detail, style) in enumerate(nodes, 1)) + '</div>')


def signal_card(plan, status):
    with st.container(border=True):
        markup('<div class="eyebrow">Engine signal · สัญญาณจาก Worker</div>')
        if not plan:
            empty("ยังไม่มีสัญญาณที่บันทึก", "Start analysis เพื่อให้ Bot วิเคราะห์และบันทึกแผน")
            return
        signal = str(plan.get("signal", "WAIT"))
        tone = "buy" if "BUY" in signal else "sell" if "SELL" in signal else "wait"
        markup(f'<div class="signal-value {tone}">{escape(signal)}</div>')
        st.caption(f'{plan.get("symbol", "")} · {plan.get("timeframe", "TF ไม่ได้บันทึก")} · {timestamp(plan.get("saved_at"))} UTC+7')
        if not status["running"]:
            st.caption("สัญญาณย้อนหลัง — Worker ไม่ได้ทำงาน")
        saved = pd.to_datetime(plan.get("saved_at"), utc=True, errors="coerce")
        if pd.notna(saved) and (pd.Timestamp.now(tz="UTC") - saved).total_seconds() > 180:
            st.warning("สัญญาณเก่ากว่า 3 นาที ตรวจเวลาข้อมูลก่อนใช้")
        st.metric("Confluence score", f'{number(plan.get("confidence"), 1)} / 100')
        st.caption("คะแนนของกฎกลยุทธ์ ไม่ใช่โอกาสชนะ")
        entry = plan.get("entry_zone", [])
        if signal != "WAIT":
            rules([("Entry zone", " – ".join(number(x) for x in entry)), ("Stop loss", number(plan.get("stop_loss"))),
                   ("TP1 / TP2", f'{number(plan.get("tp1"))} / {number(plan.get("tp2"))}'), ("TP3", number(plan.get("tp3"))),
                   ("Reward / risk", number(plan.get("rr")))])
        reason = status["last_execution"].get("reason")
        if reason:
            markup(f'<div class="signal-note">Latest execution: {escape(str(reason))}</div>')
        with st.expander("รายละเอียดสัญญาณที่บันทึก"):
            st.json(plan)


def market_view(symbol, timeframe, uploaded):
    with st.container(border=True):
        markup(f'<div class="instrument"><div class="instrument-mark">Au</div><div><strong>{escape(symbol)}</strong><div class="subtle">Technical workspace · {escape(timeframe)}</div></div></div>')
        cols = st.columns([2, 1, 1])
        kind = cols[0].radio("Price view", ["Candles", "Line"], horizontal=True, label_visibility="collapsed")
        ema = cols[1].checkbox("EMA", value=True)
        zones = cols[2].checkbox("S/R zones", value=True)
        st.caption("กราฟนี้เป็น technical preview ของ TF ที่เลือก ไม่รวมข่าว/หลาย TF จึงอาจต่างจาก Engine signal และไม่ส่งออเดอร์")
        try:
            if uploaded is not None:
                uploaded.seek(0)
                frame = pd.read_csv(uploaded)
                frame["time"] = pd.to_datetime(frame["time"], utc=True)
                result = analyze(symbol, frame)
                st.info("CSV preview — ข้อมูลนำเข้า ไม่ใช่ราคาปัจจุบันและไม่ใช้สั่งเทรด")
            else:
                result = market_preview(symbol, timeframe)
            st.plotly_chart(price_chart(result, kind, ema, zones, timeframe), width="stretch", theme=None, key="market_chart")
            last_time = result["candles"].time.iloc[-1]
            st.caption(f'เวลาเปิดแท่งล่าสุด: {timestamp(last_time)} UTC+7 • เลื่อน/ซูมกราฟได้ • Volume อาจเป็น tick volume ของ broker')
            with st.expander("ข้อมูลแท่งราคา / Download OHLC"):
                show_table(result["candles"].tail(500), "candles", "ไม่มีข้อมูลแท่งราคา")
            return result
        except (ConnectionError, ValueError, KeyError, RuntimeError, IndexError) as error:
            empty("ยังโหลดกราฟไม่ได้", "เปิด MT5 ตรวจชื่อ symbol หรืออัปโหลดไฟล์ OHLC CSV ใน sidebar")
            st.caption(f"{type(error).__name__}: {error}")
            return None


def show_table(frame, key, message):
    if frame.empty:
        empty(message, "จะแสดงรายการจากแหล่งข้อมูลจริงเมื่อมีข้อมูล")
        return
    display = frame.copy()
    for column in display:
        if isinstance(display[column].dtype, pd.DatetimeTZDtype):
            display[column] = display[column].dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(display, hide_index=True, width="stretch", height=min(460, 38 + 35 * len(display)))
    st.download_button("Download CSV", csv_bytes(display), f"aurum_{key}.csv", "text/csv", key=f"download_{key}")


def activity_feed(logs):
    st.subheader("Recent activity")
    if logs.empty:
        empty("ยังไม่มี activity", "การวิเคราะห์ การเปลี่ยนโหมด และเหตุผลที่ข้ามออเดอร์จะปรากฏที่นี่")
    for row in logs.head(5).itertuples():
        label = row.decision or row.level
        tone = "red" if row.level == "ERROR" else "gold" if label == "SKIP" else "green"
        markup(f'<div class="log-line"><div class="log-time">{escape(timestamp(row.time))}</div><div>{badge(label, tone)}</div><div class="log-message">{escape(str(row.message))}</div></div>')


def transactions(snapshot):
    st.subheader("Transactions")
    st.caption("Broker records แยกจากบันทึกในเครื่อง • เวลา Asia/Bangkok • ประวัติ broker ย้อนหลัง 7 วัน / local ล่าสุด 5,000 รายการ")
    origin = st.selectbox("แหล่งคำสั่ง", ["All", "Bot", "Manual", "Other EA"])
    tabs = st.tabs(["Open positions", "Broker deals · 7d", "Bot executions", "Paper ledger"])
    for tab, key, label in zip(tabs, ["positions", "deals", "executed", "paper"], ["ไม่มี position เปิดอยู่", "ไม่มี deal ในช่วงนี้", "ยังไม่มี execution ที่บันทึก", "ยังไม่มีรายการ paper trade"]):
        with tab:
            frame = snapshot[key]
            if key == "positions" and not snapshot["positions_available"] or key == "deals" and not snapshot["history_available"]:
                st.warning("ดึงข้อมูล broker ไม่สำเร็จ — ไม่ได้หมายความว่าไม่มีออเดอร์")
            if key in {"executed", "paper"}:
                st.caption("Local bot ledger — ไม่ใช่หลักฐานการ fill จาก broker; ตัวกรองแหล่งคำสั่งใช้เฉพาะ broker tables")
            elif origin != "All":
                frame = frame.loc[frame.origin.eq(origin)]
            show_table(frame, key, label)


database, connector = resources()
with st.sidebar:
    markup('<div class="brand"><div class="brand-mark">A</div><div><div class="brand-name">AURUM</div><div class="eyebrow">Trading control room</div></div></div>')
    page = st.radio("Workspace", ["Overview", "Market", "Transactions", "Activity", "Controls & risk"])
    st.divider()
    symbol = st.selectbox("Chart symbol", settings.symbols)
    frames = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    timeframe = st.selectbox("Chart timeframe", frames, index=frames.index(settings.timeframe) if settings.timeframe in frames else 2)
    auto_refresh = st.toggle("Refresh every 10 seconds", value=True)
    if st.button("Refresh data", width="stretch"):
        market_preview.clear()
    if st.button("Reconnect MT5", width="stretch"):
        if connector.initialize():
            market_preview.clear()
            st.success("เชื่อมต่อ MT5 แล้ว")
        else:
            st.error("เชื่อมต่อไม่สำเร็จ — ตรวจ MT5 terminal")
    with st.expander("Import chart data"):
        uploaded = st.file_uploader("OHLC CSV", type="csv")
        st.caption("time, open, high, low, close, tick_volume • เวลาไม่มี timezone จะถือเป็น UTC")
    st.divider()
    markup('<div class="session-card"><div class="eyebrow">Execution boundary</div><strong>Demo-only controller</strong><p class="subtle">หน้านี้ไม่มีปุ่มเปิด Live trading<br>การเปิดหน้าไม่เริ่ม Worker อัตโนมัติ</p></div>')
    st.caption("Local workspace · 127.0.0.1\n\nManual orders ใช้ใน MT5")


@st.fragment(run_every=10 if auto_refresh else None)
def workspace():
    snapshot = load_account_snapshot(connector, database, symbol)
    status = load_status(database)
    plan = latest_signal(database, settings.symbols[0])
    account, metrics = snapshot["account"], snapshot["metrics"]
    currency = account.get("currency", "")
    markup('<div class="eyebrow">Workspace / ' + escape(page) + '</div>')
    st.title("Trading control" if page == "Overview" else page)
    markup('<div class="subtitle">มองตลาด เห็นเหตุผล และควบคุมระบบเทรดจากจุดเดียว</div>')
    account_label = "DEMO VERIFIED" if snapshot["is_demo"] else "NON-DEMO · AUTO BLOCKED" if snapshot["is_demo"] is False else "ACCOUNT UNKNOWN"
    markup('<div class="badge-row">' + badge(account_label, "green" if snapshot["is_demo"] else "gold") + badge(status["state"], "green" if status["running"] else "gray") + badge(status["mode"], "gold") + badge(f'{snapshot["as_of"]:%H:%M:%S} UTC+7') + '</div>')
    notice = st.session_state.pop("control_notice", None)
    if notice:
        st.success(notice)
    if status["last_error"]:
        st.error(f'Worker: {status["last_error"]}')
    if snapshot["errors"]:
        with st.expander("Data status — ข้อมูลบางส่วนยังไม่พร้อม", expanded=not snapshot["connected"]):
            for error in snapshot["errors"]:
                st.warning(error)
    if page in {"Overview", "Controls & risk"}:
        cols = st.columns(4)
        cols[0].metric(f"Account balance · {currency}", number(metrics["balance"]))
        cols[1].metric(f"Account equity · {currency}", number(metrics["equity"]))
        cols[2].metric(f"Bot P/L today + floating · {currency}", number(metrics["daily_pnl"]))
        cols[3].metric("Open bot positions", number(metrics["bot_open_positions"], 0))
        st.caption(f'P/L วันปฏิทิน Bangkok รวม commission/swap/fee • Bot entries วันนี้: {number(metrics["trades_today"], 0)} • Risk engine ใช้วัน UTC')
        flow(status, snapshot, plan)
    if page == "Overview":
        left, right = st.columns([2.4, 1], gap="large")
        with left:
            market_view(symbol, timeframe, uploaded)
        with right:
            signal_card(plan, status)
            if st.button("Open execution controls", width="stretch"):
                st.session_state["show_controls"] = not st.session_state.get("show_controls", False)
            if st.session_state.get("show_controls"):
                controller(database, connector, status, snapshot)
        left, right = st.columns([1, 1], gap="large")
        with left, st.container(border=True):
            st.subheader("Net realized P/L · 7 days")
            st.caption(f'Bot only · {currency} · รวมต้นทุนที่ broker บันทึก ไม่ใช่กราฟ equity')
            if snapshot["history_available"] and not snapshot["deals"].loc[lambda df: df.origin.eq("Bot")].empty:
                st.plotly_chart(pnl_chart(snapshot["pnl_curve"]), width="stretch", theme=None)
                with st.expander("P/L data"):
                    show_table(snapshot["pnl_curve"], "pnl", "ยังไม่มีข้อมูล P/L")
            else:
                empty("ยังไม่มีประวัติ P/L ของ Bot", "กราฟเริ่มแสดงเมื่อมี deal ของ Bot และเชื่อมต่อ history ได้")
        with right, st.container(border=True):
            activity_feed(snapshot["logs"])
    elif page == "Market":
        result = market_view(symbol, timeframe, uploaded)
        if result:
            left, right = st.columns([1.3, 1])
            with left, st.container(border=True):
                st.subheader("Technical score breakdown")
                st.plotly_chart(signal_chart(result["components"]), width="stretch", theme=None)
                st.caption("Signed weighted contributions · News / multi-timeframe ไม่ได้คำนวณใน preview นี้")
                with st.expander("Score data"):
                    st.dataframe(pd.DataFrame(result["components"].items(), columns=["Factor", "Raw score"]), hide_index=True)
            with right:
                signal_card(plan, status)
        with st.expander("Stored news · ข่าวที่ Worker บันทึก"):
            show_table(pd.DataFrame(database.rows("news")), "news", "ยังไม่มีข่าวที่บันทึก")
    elif page == "Transactions":
        transactions(snapshot)
    elif page == "Activity":
        st.subheader("Event log")
        st.caption("ล่าสุด 5,000 รายการ • เวลา Bangkok • แสดงเหตุผลที่ส่ง/ข้ามออเดอร์และการควบคุม Worker")
        cols = st.columns([1, 1, 2])
        level = cols[0].selectbox("Level", ["All", "INFO", "WARNING", "ERROR"])
        decision = cols[1].selectbox("Decision", ["All", "SKIP", "EXECUTE"])
        query = cols[2].text_input("Search logs", placeholder="symbol, reason, ticket…")
        logs = snapshot["logs"]
        if level != "All":
            logs = logs.loc[logs.level.eq(level)]
        if decision != "All":
            logs = logs.loc[logs.decision.eq(decision)]
        if query:
            logs = logs.loc[logs.astype(str).agg(" ".join, axis=1).str.contains(query, case=False, regex=False)]
        show_table(logs, "activity", "ไม่พบ log ตามตัวกรอง")
    else:
        left, right = st.columns([1.15, 1], gap="large")
        with left, st.container(border=True):
            controller(database, connector, status, snapshot)
        with right, st.container(border=True):
            st.subheader("Risk guardrails")
            st.caption("ค่าปัจจุบันจาก config · read-only • แก้ .env และ restart Worker / UI เพื่อโหลดค่าใหม่")
            rules([("Risk per trade / max", f"{settings.risk_per_trade:.1%} / {settings.max_risk_per_trade:.1%}"),
                   ("Daily loss limit · UTC", f"{settings.max_daily_loss:.1%}"), ("Min score / reward:risk", f"{settings.min_confidence:g} / {settings.min_rr:g}"),
                   ("Positions · all / per symbol", f"{settings.max_positions} / {settings.max_positions_per_symbol}"),
                   ("Daily entries / cooldown", f"{settings.max_trades_per_day} / {settings.trade_cooldown_minutes} min"),
                   ("Max spread", f"{settings.max_spread_points:g} points"), ("Sizing", "Risk-based · broker lot step"),
                   ("Account leverage", f'1:{account["leverage"]}' if account.get("leverage") else "—"),
                   ("Free margin", f'{number(metrics["free_margin"])} {currency}')])
            st.caption("Leverage เปลี่ยนที่ broker ไม่ใช่ต่อออเดอร์ • SL/TP มาจากแผน Bot • ไม่มีการรับประกันกำไร")
            st.subheader("Worker health")
            rules([("Process ID", status.get("pid") or "—"), ("Phase", status["phase"]),
                   ("Heartbeat", timestamp(status["heartbeat_at"])), ("Control source", status["mode_source"])])
    markup('<div class="footer"><span>AURUM / Local trading workspace</span><span>Demo execution only from this controller · Asia/Bangkok (UTC+7)</span></div>')


workspace()
