# AI-Assisted MT5 Trading Bot (V1)

ระบบวิเคราะห์และ paper trading แบบ rule-based สำหรับ MetaTrader 5 ใช้ technical confluence, support/resistance, multi-timeframe, ข่าว GDELT + FinBERT, risk management, SQLite, backtest และ Streamlit dashboard โดยค่าเริ่มต้น **ไม่ส่งเงินจริง**

> ซอฟต์แวร์นี้เป็นเครื่องมือวิจัย ไม่ใช่คำแนะนำการลงทุน ทดสอบกับบัญชี Demo และข้อมูลของ broker ก่อนใช้งานทุกครั้ง

## Architecture

```text
MT5/CSV → indicators + trend + zones + price action
       → multi-timeframe + optional GDELT/FinBERT
       → weighted signal → SL/TP + risk checks
       → paper SQLite หรือ guarded MT5 order
       → Streamlit dashboard / backtest metrics
```

- `mt5/`: connection, OHLC/tick data, guarded order execution
- `analyzers/`: indicators, trend, swing-zone clustering, Fibonacci, breakout/retest, candle, volume, multi-timeframe
- `strategy/`: configurable confluence score และ trade plan
- `risk/`: ATR/structure stops, RR targets, broker-aware lot sizing, trade limits
- `news/`: async GDELT และ lazy-loaded FinBERT; ข่าวล่มแล้ว technical analysis ยังทำงาน
- `database/`: SQLite schema และ persistence
- `backtest/`: single-position conservative OHLC engine และ performance metrics
- `dashboard/`: Plotly candlestick, EMA, zones, entry/SL/TP, signal/news/performance

## Requirements

- Python 3.11+
- Windows + MetaTrader 5 terminal สำหรับ live market data/order (แพ็กเกจ Python ของ MT5 รองรับ Windows อย่างเป็นทางการ)
- macOS/Linux ยังรัน CSV backtest, analysis และ dashboard ด้วย CSV ได้

## Installation

```bash
cd trading_bot
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

### TA-Lib

ตัวระบบ V1 ใช้ Pandas/NumPy เป็น portable calculation path แต่ติดตั้ง TA-Lib ตาม technology stack เพื่อรองรับการเทียบผล/ขยาย strategy:

- Windows: `pip install TA-Lib` (wheel รุ่นปัจจุบันรวม native library ใน platform ที่รองรับ)
- macOS: `brew install ta-lib && pip install TA-Lib`
- Ubuntu/Debian: ติดตั้ง native TA-Lib จาก source/package ของ distribution แล้ว `pip install TA-Lib`

ถ้าไม่ต้องการ FinBERT ให้ตั้ง `USE_FINBERT=false` และสามารถไม่ติดตั้ง `torch transformers` เพื่อลดขนาด environment

## MT5 Setup

1. เปิด MT5 terminal และ login บัญชี Demo
2. เปิด symbol ที่ broker ใช้จริงใน Market Watch (ชื่อหุ้นบาง broker มี suffix)
3. คัดลอก `.env.example` เป็น `.env` แล้วใส่ `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`
4. เปิด Algo Trading ใน terminal เฉพาะเมื่อผ่าน demo test แล้ว

ค่าเริ่มต้นสำคัญ:

```dotenv
DEMO_MODE=true
LIVE_TRADING=false
RISK_PER_TRADE=0.01
MAX_RISK_PER_TRADE=0.02
MAX_DAILY_LOSS=0.03
MIN_RR=2
```

Live order เกิดได้เฉพาะเมื่อตั้ง `DEMO_MODE=false`, `LIVE_TRADING=true`, MT5 เชื่อมต่อสำเร็จ และ `RiskManager` อนุมัติ ผู้ใช้ต้องเปลี่ยนสองค่านี้เอง

## Run

### Native MT5 Expert Advisor (Demo only)

`mql5/AurumXAU_EA.mq5` คือ EA ที่วิเคราะห์และส่งคำสั่งจากใน MT5 โดยตรง จึงไม่ต้องเปิด Python หรือ Dashboard ขณะทำงาน ค่าเริ่มต้นเป็น `MANUAL`, risk-based volume `0.5%` และรับเฉพาะบัญชี Demo/Strategy Tester

1. คัดลอกไฟล์ `.mq5` และ `.ex5` ไป `MQL5/Experts/Aurum/` ใน MT5 Data Folder
2. ใน Navigator กด Refresh แล้วลาก `AurumXAU_EA` ลงกราฟ XAUUSD
3. เปิด Algo Trading จากนั้นกด `AUTO DEMO` บนกราฟเมื่อต้องการให้ EA เปิดออเดอร์เอง
4. กด `MANUAL` เพื่อวิเคราะห์ต่อแต่ไม่เปิดออเดอร์ใหม่ หรือ `PAUSE` เพื่อพักทั้งการวิเคราะห์และการเข้าออเดอร์

เลือก `LOT_FIXED` สำหรับ lot คงที่ 0.01 หรือ `LOT_RISK_PERCENT` เพื่อคำนวณจาก Balance และระยะ SL (default 0.5%, hard cap 1%) ค่า leverage เป็นคุณสมบัติของบัญชีที่ broker กำหนด ไม่ได้ตั้งต่อออเดอร์ EA v2 ใช้ H1 trend + M15 structure/SR, EMA, ADX, RSI context, candle confirmation และ volatility filter พร้อม daily/consecutive-loss guard, cooldown, margin check และ break-even

วิเคราะห์ symbol จาก MT5 และบันทึก signal/news ลง SQLite:

```bash
python main.py --symbol XAUUSD
```

### Show signals on the MT5 chart

1. Copy `mql5/TradingBotOverlay.mq5` to the terminal Data Folder under `MQL5/Indicators/`, compile it in MetaEditor, and attach it to the matching symbol chart.
2. Keep the analyzer running using the broker's exact symbol name, including any suffix:

```bash
python main.py --symbol XAUUSD --watch 60
```

The indicator reads `Common/Files/TradingBot/signal.csv` and draws the current entry zone, SL, TP1-TP3, nearest support/resistance, and BUY/SELL arrow. It does not place orders.

Automatic execution is off by default. `AUTO_TRADE=true` enables risk-based sizing from account balance, SL distance, and broker volume rules. With `DEMO_MODE=true` and `LIVE_TRADING=false`, orders are sent only when MT5 confirms the connected account is a Demo account. Keep `AUTO_TRADE=false` for manual trading. Account leverage is set by the broker, not per order.

Dashboard:

```bash
streamlit run dashboard/app.py
```

Dashboard ใช้ MT5 หากเชื่อมต่ออยู่ หรืออัปโหลด CSV ที่มี `time,open,high,low,close,tick_volume` ได้ กราฟมี hover สำหรับเวลา ราคา EMA และเส้น/zone ของแผนเทรด

## Backtest

```bash
python main.py --symbol NVDA --backtest data/NVDA_M15.csv
```

Backtest V1 เปิดครั้งละหนึ่ง position และถ้า SL/TP ถูกแตะใน candle เดียวกันจะนับ SL ก่อนแบบ conservative รายงาน total return, win/loss rate, profit factor, Sharpe, max drawdown, average win/loss, RR, trades และ expectancy

### MT5 A/B backtest

ไฟล์ `backtest/mt5_baseline.ini` และ `backtest/mt5_no_break_even.ini` ใช้ XAUUSD M15, real ticks และช่วงเวลาเดียวกัน โดยต่างกันเฉพาะ `UseBreakEven` คัดลอกไฟล์ `.set` ที่เกี่ยวข้องไป `MQL5/Profiles/Tester/` แล้วเปิด MT5 ด้วย `/config:<ไฟล์.ini>` ผลรอบล่าสุดอยู่ที่ `backtest/reports/comparison.csv`

Preset ทุนขนาดเล็กอยู่ที่ `backtest/mt5_budget_10.ini`, `mt5_budget_50.ini` และ `mt5_budget_100.ini` ทั้งหมดคง risk guard เดิมไว้ ดังนั้น XAUUSD มาตรฐานอาจไม่มีออเดอร์ เปลี่ยน `Symbol` เมื่อเชื่อมบัญชี cent/nano ของ broker จริงแล้วเท่านั้น

## Tests

```bash
pytest
```

ครอบคลุม indicator calculation, DBSCAN support/resistance, position sizing, risk filters, ATR stop, RR targets และ signal scoring

## Data caveats

- `tick_volume` ของ MT5 หลาย broker คือจำนวนการเปลี่ยน tick ไม่ใช่ exchange volume จริง ระบบเลือก `real_volume` เมื่อมีค่า
- หุ้น/CFD มี symbol specification, session, tick value และ suffix ต่างกัน ต้องใช้ค่าจาก `mt5.symbol_info()` ในการคำนวณ lot จริง
- FinBERT ดาวน์โหลดโมเดล Hugging Face ครั้งแรกและอาจใช้ RAM มาก ปิดได้โดยไม่กระทบ technical analysis
- GDELT เป็นแหล่งข่าวฟรีและอาจ timeout; ระบบคืน sentiment กลางและทำงานต่อ
