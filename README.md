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

วิเคราะห์ symbol จาก MT5 และบันทึก signal/news ลง SQLite:

```bash
python main.py --symbol NVDA
```

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
