#property copyright "Aurum Trading Control"
#property version   "2.10"
#property strict

#include <Trade/Trade.mqh>

enum LOT_MODE { LOT_FIXED, LOT_RISK_PERCENT };
enum EA_MODE  { MODE_MANUAL, MODE_AUTO_DEMO, MODE_PAUSED };

input group "Safety and execution"
input EA_MODE  StartupMode              = MODE_MANUAL;
input ulong    MagicNumber              = 2601001;
input int      MaxSpreadPoints          = 50;
input int      MaxTradesPerDay          = 5;
input double   MaxDailyLossPercent      = 2.0;
input int      MaxPositionsPerSymbol    = 1;
input bool     AllowHedging             = false;
input int      TradeCooldownBars        = 2;
input int      MaxConsecutiveLosses     = 3;
input int      LossCooldownBars         = 8;
input int      SlippagePoints           = 20;
input double   MarginSafetyMultiple     = 1.20;

input group "Position sizing"
input LOT_MODE VolumeMode               = LOT_RISK_PERCENT;
input double   FixedVolume              = 0.01;
input double   RiskPerTrade             = 0.50;
input double   MaxRiskPerTrade          = 1.00;

input group "Signal and trend"
input ENUM_TIMEFRAMES SignalTimeframe   = PERIOD_M15;
input ENUM_TIMEFRAMES TrendTimeframe    = PERIOD_H1;
input double   MinConfidence            = 75.0;
input double   MinRR                     = 2.0;
input double   MinADX                    = 20.0;
input int      StructureLookback        = 40;
input double   MaxZoneDistanceATR       = 0.80;
input double   EMAFlatThresholdATR      = 0.05;

input group "Stops and volatility"
input int      ATRPeriod                = 14;
input double   ATRStopMultiplier        = 0.30;
input double   MaxSLATR                 = 3.0;
input double   MinATRNormalized         = 0.00015;
input double   MaxATRNormalized         = 0.00600;

input group "Position management"
input bool     UseBreakEven             = true;
input double   BreakEvenTriggerR        = 1.0;
input int      BreakEvenBufferPoints    = 5;
input bool     UseTrailingStop          = false;
input double   TrailingATRMultiplier    = 1.5;

input group "Optional filters (broker server time)"
input bool     UseSessionFilter         = false;
input int      SessionStartHour         = 7;
input int      SessionEndHour           = 22;
input bool     UseNewsFilter            = false;
input int      NewsBlockMinutesBefore   = 30;
input int      NewsBlockMinutesAfter    = 15;

CTrade trade;
EA_MODE current_mode;
int ema20_handle=INVALID_HANDLE, ema50_handle=INVALID_HANDLE, ema200_handle=INVALID_HANDLE;
int h1ema50_handle=INVALID_HANDLE, h1ema200_handle=INVALID_HANDLE;
int rsi_handle=INVALID_HANDLE, adx_handle=INVALID_HANDLE, atr_handle=INVALID_HANDLE;
datetime last_bar=0;
string prefix="AurumEA_";

struct Setup
{
   int direction;
   double score,entry,stop,take,atr;
   string reasons;
};

string ModeText()
{
   if(current_mode==MODE_AUTO_DEMO) return "AUTO DEMO";
   if(current_mode==MODE_PAUSED) return "PAUSED";
   return "MANUAL";
}

bool IsDemoOrTester()
{
   if(MQLInfoInteger(MQL_TESTER)) return true;
   return (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;
}

void Label(const string name,const string text,const int x,const int y,const color colour,const int size=9)
{
   string id=prefix+name;
   if(ObjectFind(0,id)<0) ObjectCreate(0,id,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,id,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,id,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,id,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,id,OBJPROP_COLOR,colour);
   ObjectSetInteger(0,id,OBJPROP_FONTSIZE,size);
   ObjectSetString(0,id,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,id,OBJPROP_TEXT,text);
}

void Button(const string name,const string text,const int x,const color background)
{
   string id=prefix+name;
   if(ObjectFind(0,id)<0) ObjectCreate(0,id,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,id,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,id,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,id,OBJPROP_YDISTANCE,66);
   ObjectSetInteger(0,id,OBJPROP_XSIZE,86);
   ObjectSetInteger(0,id,OBJPROP_YSIZE,28);
   ObjectSetInteger(0,id,OBJPROP_BGCOLOR,background);
   ObjectSetInteger(0,id,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,id,OBJPROP_BORDER_COLOR,clrDimGray);
   ObjectSetString(0,id,OBJPROP_TEXT,text);
}

void PriceLine(const string name,const double price,const color colour,const ENUM_LINE_STYLE style)
{
   string id=prefix+name;
   if(price<=0) { ObjectDelete(0,id); return; }
   if(ObjectFind(0,id)<0) ObjectCreate(0,id,OBJ_HLINE,0,0,price);
   ObjectSetDouble(0,id,OBJPROP_PRICE,price);
   ObjectSetInteger(0,id,OBJPROP_COLOR,colour);
   ObjectSetInteger(0,id,OBJPROP_STYLE,style);
   ObjectSetInteger(0,id,OBJPROP_SELECTABLE,false);
   ObjectSetString(0,id,OBJPROP_TOOLTIP,name+" "+DoubleToString(price,_Digits));
}

void DrawPanel(const string detail="")
{
   color state=current_mode==MODE_AUTO_DEMO?clrMediumSeaGreen:current_mode==MODE_PAUSED?clrOrange:clrSilver;
   Label("Title","AURUM EA v2.1  |  "+_Symbol+"  |  "+EnumToString(SignalTimeframe),14,14,clrGold,11);
   Label("State","MODE: "+ModeText()+"  |  Account: "+(IsDemoOrTester()?"DEMO/TESTER":"NON-DEMO"),14,40,state,9);
   Label("Detail",detail,14,103,clrLightSteelBlue,8);
   Button("Auto","AUTO DEMO",14,current_mode==MODE_AUTO_DEMO?clrSeaGreen:clrDarkSlateGray);
   Button("Manual","MANUAL",106,current_mode==MODE_MANUAL?clrSteelBlue:clrDarkSlateGray);
   Button("Pause","PAUSE",198,current_mode==MODE_PAUSED?clrDarkOrange:clrDarkSlateGray);
   ChartRedraw();
}

void LogSkip(const string reason,const string detail="")
{
   Print("AURUM_SKIP|",TimeToString(iTime(_Symbol,SignalTimeframe,1)),"|",reason,"|",detail);
   DrawPanel(reason+(detail==""?"":" | "+detail));
}

bool Value(const int handle,const int buffer,const int shift,double &value)
{
   double data[1];
   if(CopyBuffer(handle,buffer,shift,1,data)!=1) return false;
   value=data[0];
   return MathIsValidNumber(value) && value!=EMPTY_VALUE;
}

double Highest(const int first,const int count)
{
   double value=-DBL_MAX;
   for(int i=first;i<first+count;i++) value=MathMax(value,iHigh(_Symbol,SignalTimeframe,i));
   return value;
}

double Lowest(const int first,const int count)
{
   double value=DBL_MAX;
   for(int i=first;i<first+count;i++) value=MathMin(value,iLow(_Symbol,SignalTimeframe,i));
   return value;
}

bool BullishCandle()
{
   double o1=iOpen(_Symbol,SignalTimeframe,1),c1=iClose(_Symbol,SignalTimeframe,1);
   double h1=iHigh(_Symbol,SignalTimeframe,1),l1=iLow(_Symbol,SignalTimeframe,1);
   double o2=iOpen(_Symbol,SignalTimeframe,2),c2=iClose(_Symbol,SignalTimeframe,2);
   double range=h1-l1,body=MathAbs(c1-o1),lower=MathMin(o1,c1)-l1;
   bool engulf=c1>o1 && c2<o2 && c1>=o2 && o1<=c2;
   bool rejection=c1>o1 && lower>=body*1.5;
   bool strong=c1>o1 && range>0 && body/range>=0.55 && c1>=h1-range*0.2;
   return engulf || rejection || strong;
}

bool BearishCandle()
{
   double o1=iOpen(_Symbol,SignalTimeframe,1),c1=iClose(_Symbol,SignalTimeframe,1);
   double h1=iHigh(_Symbol,SignalTimeframe,1),l1=iLow(_Symbol,SignalTimeframe,1);
   double o2=iOpen(_Symbol,SignalTimeframe,2),c2=iClose(_Symbol,SignalTimeframe,2);
   double range=h1-l1,body=MathAbs(c1-o1),upper=h1-MathMax(o1,c1);
   bool engulf=c1<o1 && c2>o2 && c1<=o2 && o1>=c2;
   bool rejection=c1<o1 && upper>=body*1.5;
   bool strong=c1<o1 && range>0 && body/range>=0.55 && c1<=l1+range*0.2;
   return engulf || rejection || strong;
}

bool SessionAllowed()
{
   if(!UseSessionFilter) return true;
   MqlDateTime now; TimeToStruct(TimeCurrent(),now);
   if(SessionStartHour==SessionEndHour) return true;
   if(SessionStartHour<SessionEndHour) return now.hour>=SessionStartHour && now.hour<SessionEndHour;
   return now.hour>=SessionStartHour || now.hour<SessionEndHour;
}

bool HighImpactUSDNews()
{
   if(!UseNewsFilter || MQLInfoInteger(MQL_TESTER)) return false;
   MqlCalendarValue values[];
   datetime from=TimeTradeServer()-NewsBlockMinutesAfter*60;
   datetime to=TimeTradeServer()+NewsBlockMinutesBefore*60;
   int count=CalendarValueHistory(values,from,to,NULL,"USD");
   if(count<=0) return false;
   for(int i=0;i<count;i++)
   {
      MqlCalendarEvent event;
      if(CalendarEventById(values[i].event_id,event) && event.importance==CALENDAR_IMPORTANCE_HIGH) return true;
   }
   return false;
}

bool BuildSetup(Setup &setup,string &skip)
{
   setup.direction=0; setup.score=0; setup.reasons="";
   double ema20,ema20prev,ema50,ema200,h1ema50,h1ema200,rsi,rsi_prev,adx,atr;
   if(!Value(ema20_handle,0,1,ema20) || !Value(ema20_handle,0,2,ema20prev) ||
      !Value(ema50_handle,0,1,ema50) || !Value(ema200_handle,0,1,ema200) ||
      !Value(h1ema50_handle,0,1,h1ema50) || !Value(h1ema200_handle,0,1,h1ema200) ||
      !Value(rsi_handle,0,1,rsi) || !Value(rsi_handle,0,2,rsi_prev) ||
      !Value(adx_handle,0,1,adx) || !Value(atr_handle,0,1,atr) || atr<=0)
   { skip="SKIP_INDICATOR_DATA"; return false; }

   double close=iClose(_Symbol,SignalTimeframe,1);
   double h1close=iClose(_Symbol,TrendTimeframe,1);
   if(close<=0 || h1close<=0) { skip="SKIP_PRICE_DATA"; return false; }
   setup.direction=(h1ema50>h1ema200 && h1close>h1ema50)?1:(h1ema50<h1ema200 && h1close<h1ema50)?-1:0;
   if(setup.direction==0) { skip="SKIP_HTF_MIXED"; return false; }
   setup.score=20; setup.atr=atr; setup.entry=close; setup.reasons=setup.direction>0?"HTF_BULL":"HTF_BEAR";

   int half=MathMax(5,StructureLookback/2);
   double recent_high=Highest(2,half),old_high=Highest(2+half,half);
   double recent_low=Lowest(2,half),old_low=Lowest(2+half,half);
   bool bull_structure=recent_high>old_high && recent_low>old_low;
   bool bear_structure=recent_high<old_high && recent_low<old_low;
   double zone_support=Lowest(2,MathMin(12,StructureLookback));
   double zone_resistance=Highest(2,MathMin(12,StructureLookback));
   double prior_high=Highest(3,StructureLookback),prior_low=Lowest(3,StructureLookback);
   bool bull_retest=iClose(_Symbol,SignalTimeframe,2)>prior_high && iLow(_Symbol,SignalTimeframe,1)<=prior_high+atr*MaxZoneDistanceATR && close>prior_high;
   bool bear_retest=iClose(_Symbol,SignalTimeframe,2)<prior_low && iHigh(_Symbol,SignalTimeframe,1)>=prior_low-atr*MaxZoneDistanceATR && close<prior_low;
   // A confirmed pullback to aligned moving averages is dynamic market structure,
   // not a lower confidence threshold. Candle confirmation remains mandatory below.
   bool bull_pullback=ema20>ema50 && close>=ema50 && iLow(_Symbol,SignalTimeframe,1)<=ema20+atr*MaxZoneDistanceATR && close>ema20;
   bool bear_pullback=ema20<ema50 && close<=ema50 && iHigh(_Symbol,SignalTimeframe,1)>=ema20-atr*MaxZoneDistanceATR && close<ema20;
   bool dynamic_pullback=setup.direction>0?bull_pullback:bear_pullback;
   bool structure=setup.direction>0?(bull_structure||bull_retest||bull_pullback):(bear_structure||bear_retest||bear_pullback);
   if(!structure) { skip="SKIP_MIXED_STRUCTURE"; return false; }
   setup.score+=15;
   if(dynamic_pullback) setup.reasons+=setup.direction>0?"|EMA_PULLBACK_BUY":"|EMA_PULLBACK_SELL";
   else setup.reasons+=setup.direction>0?(bull_retest?"|BULL_RETEST":"|HH_HL"):(bear_retest?"|BEAR_RETEST":"|LH_LL");

   double zone_distance=setup.direction>0?(close-zone_support)/atr:(zone_resistance-close)/atr;
   bool near_zone=zone_distance>=0 && zone_distance<=MaxZoneDistanceATR;
   bool retest=setup.direction>0?bull_retest:bear_retest;
   if(!near_zone && !retest && !dynamic_pullback) { skip="SKIP_FAR_FROM_ZONE"; return false; }
   setup.score+=20;
   setup.reasons+=dynamic_pullback?"|DYNAMIC_SR":setup.direction>0?"|SUPPORT_RETEST":"|RESIST_REJECT";

   bool ema_align=setup.direction>0?(ema20>ema50 && close>ema200-atr*0.3):(ema20<ema50 && close<ema200+atr*0.3);
   if(!ema_align || MathAbs(ema20-ema20prev)<atr*EMAFlatThresholdATR) { skip="SKIP_EMA_SIDEWAY"; return false; }
   setup.score+=10; setup.reasons+="|EMA_ALIGN";
   if(adx<MinADX) { skip="SKIP_LOW_ADX"; return false; }
   setup.score+=adx>=25?8:4; setup.reasons+="|ADX_OK";

   bool rsi_context=setup.direction>0?(rsi>=35 && rsi<=55 && rsi>rsi_prev):(rsi>=45 && rsi<=65 && rsi<rsi_prev);
   if(rsi_context) { setup.score+=7; setup.reasons+=setup.direction>0?"|RSI_PULLBACK":"|RSI_REJECT"; }
   bool candle=setup.direction>0?BullishCandle():BearishCandle();
   if(!candle) { skip="SKIP_NO_CANDLE_CONFIRMATION"; return false; }
   setup.score+=10; setup.reasons+="|CANDLE_OK";

   double atr_normalized=atr/close;
   if(atr_normalized<MinATRNormalized) { skip="SKIP_LOW_VOLATILITY"; return false; }
   if(atr_normalized>MaxATRNormalized) { skip="SKIP_HIGH_VOLATILITY"; return false; }
   setup.score+=5;
   if(retest) setup.score+=5;
   if(setup.score<MinConfidence) { skip="SKIP_CONFIDENCE"; return false; }

   double structure_level=setup.direction>0?zone_support:zone_resistance;
   if(dynamic_pullback && !near_zone && !retest)
      structure_level=setup.direction>0?Lowest(1,5):Highest(1,5);
   setup.stop=setup.direction>0?structure_level-atr*ATRStopMultiplier:structure_level+atr*ATRStopMultiplier;
   double risk=MathAbs(close-setup.stop);
   if(risk<=SymbolInfoDouble(_Symbol,SYMBOL_POINT)) { skip="SKIP_INVALID_SL"; return false; }
   if(risk>atr*MaxSLATR) { skip="SKIP_SL_TOO_WIDE"; return false; }
   setup.take=close+setup.direction*risk*MinRR;
   double opposing=setup.direction>0?zone_resistance:zone_support;
   if((setup.direction>0 && opposing>close && opposing<setup.take) || (setup.direction<0 && opposing<close && opposing>setup.take))
   { skip="SKIP_RR_BLOCKED_BY_STRUCTURE"; return false; }
   return true;
}

datetime DayStart()
{
   MqlDateTime now; TimeToStruct(TimeCurrent(),now);
   now.hour=0; now.min=0; now.sec=0;
   return StructToTime(now);
}

double OwnFloatingProfit()
{
   double pnl=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket>0 && (ulong)PositionGetInteger(POSITION_MAGIC)==MagicNumber)
         pnl+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
   }
   return pnl;
}

void DailyHistory(int &entries,double &pnl)
{
   entries=0; pnl=0;
   if(!HistorySelect(DayStart(),TimeCurrent())) return;
   ulong seen_orders[];
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber) continue;
      pnl+=HistoryDealGetDouble(ticket,DEAL_PROFIT)+HistoryDealGetDouble(ticket,DEAL_COMMISSION)+HistoryDealGetDouble(ticket,DEAL_SWAP)+HistoryDealGetDouble(ticket,DEAL_FEE);
      ENUM_DEAL_ENTRY type=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(type==DEAL_ENTRY_IN || type==DEAL_ENTRY_INOUT)
      {
         ulong order=(ulong)HistoryDealGetInteger(ticket,DEAL_ORDER);
         bool duplicate=false;
         for(int j=0;j<ArraySize(seen_orders);j++) if(seen_orders[j]==order) { duplicate=true; break; }
         if(!duplicate) { int n=ArraySize(seen_orders); ArrayResize(seen_orders,n+1); seen_orders[n]=order; entries++; }
      }
   }
}

void ExitHistory(int &losses,datetime &last_exit)
{
   losses=0; last_exit=0;
   if(!HistorySelect(TimeCurrent()-86400*90,TimeCurrent())) return;
   ulong positions[]; double results[]; datetime exit_times[];
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=MagicNumber || HistoryDealGetString(ticket,DEAL_SYMBOL)!=_Symbol) continue;
      ENUM_DEAL_ENTRY type=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(type!=DEAL_ENTRY_OUT && type!=DEAL_ENTRY_OUT_BY && type!=DEAL_ENTRY_INOUT) continue;
      ulong position=(ulong)HistoryDealGetInteger(ticket,DEAL_POSITION_ID);
      double result=HistoryDealGetDouble(ticket,DEAL_PROFIT)+HistoryDealGetDouble(ticket,DEAL_COMMISSION)+HistoryDealGetDouble(ticket,DEAL_SWAP)+HistoryDealGetDouble(ticket,DEAL_FEE);
      int found=-1;
      for(int j=0;j<ArraySize(positions);j++) if(positions[j]==position) { found=j; break; }
      if(found<0)
      {
         found=ArraySize(positions); ArrayResize(positions,found+1); ArrayResize(results,found+1); ArrayResize(exit_times,found+1);
         positions[found]=position; results[found]=0;
      }
      results[found]+=result;
      exit_times[found]=(datetime)HistoryDealGetInteger(ticket,DEAL_TIME);
   }
   for(int i=ArraySize(positions)-1;i>=0;i--)
   {
      if(last_exit==0) last_exit=exit_times[i];
      if(results[i]<0) losses++; else if(results[i]>0) break;
   }
}

int OwnPositions()
{
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket>0 && PositionGetString(POSITION_SYMBOL)==_Symbol && (ulong)PositionGetInteger(POSITION_MAGIC)==MagicNumber) count++;
   }
   return count;
}

bool HasPositionConflict(const int direction)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)==MagicNumber) return true;
      ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      bool opposite=(direction>0 && type==POSITION_TYPE_SELL) || (direction<0 && type==POSITION_TYPE_BUY);
      if(opposite && !AllowHedging) return true;
   }
   return false;
}

double NormalizeVolume(double volume)
{
   double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(step<=0) return 0;
   volume=MathFloor(volume/step+1e-9)*step;
   if(volume<minimum) return 0;
   return MathMin(maximum,NormalizeDouble(volume,8));
}

bool CalculateVolume(const Setup &setup,double price,double &volume,string &skip)
{
   ENUM_ORDER_TYPE type=setup.direction>0?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   double one_lot_loss=0;
   if(!OrderCalcProfit(type,_Symbol,1.0,price,setup.stop,one_lot_loss) || one_lot_loss==0) { skip="SKIP_VOLUME_CALC"; return false; }
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   double requested=VolumeMode==LOT_FIXED?FixedVolume:balance*RiskPerTrade/100.0/MathAbs(one_lot_loss);
   volume=NormalizeVolume(requested);
   if(volume<=0)
   {
      double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),min_loss=0;
      if(!OrderCalcProfit(type,_Symbol,minimum,price,setup.stop,min_loss)) { skip="SKIP_VOLUME_CALC"; return false; }
      skip=MathAbs(min_loss)>balance*MaxRiskPerTrade/100.0?"SKIP_MIN_LOT_RISK":"SKIP_VOLUME_BELOW_MIN";
      return false;
   }
   double actual_loss=0;
   if(!OrderCalcProfit(type,_Symbol,volume,price,setup.stop,actual_loss) || MathAbs(actual_loss)>balance*MaxRiskPerTrade/100.0)
   { skip="SKIP_MAX_RISK"; return false; }
   double margin=0;
   if(!OrderCalcMargin(type,_Symbol,volume,price,margin) || margin*MarginSafetyMultiple>AccountInfoDouble(ACCOUNT_MARGIN_FREE))
   { skip="SKIP_NOT_ENOUGH_MARGIN"; return false; }
   return true;
}

string ExecutionBlock(const datetime signal_bar,const int direction)
{
   if(current_mode!=MODE_AUTO_DEMO) return "ANALYSIS_ONLY";
   if(!IsDemoOrTester()) return "SKIP_DEMO_ACCOUNT_REQUIRED";
   if(!MQLInfoInteger(MQL_TESTER) && (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))) return "SKIP_ALGO_TRADING_DISABLED";
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return "SKIP_TICK_UNAVAILABLE";
   double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   double spread=point>0?(tick.ask-tick.bid)/point:DBL_MAX;
   if(spread>MaxSpreadPoints) return "SKIP_HIGH_SPREAD";
   if(!SessionAllowed()) return "SKIP_OUTSIDE_SESSION";
   if(HighImpactUSDNews()) return "SKIP_HIGH_IMPACT_NEWS";
   if(OwnPositions()>=MaxPositionsPerSymbol || HasPositionConflict(direction)) return "SKIP_EXISTING_POSITION";
   string key="Aurum.LastBar."+IntegerToString((int)MagicNumber)+"."+_Symbol+"."+IntegerToString((int)SignalTimeframe);
   if(GlobalVariableCheck(key) && (datetime)GlobalVariableGet(key)==signal_bar) return "SKIP_DUPLICATE_CANDLE";
   int entries,losses; double pnl; datetime last_exit;
   DailyHistory(entries,pnl);
   ExitHistory(losses,last_exit);
   if(entries>=MaxTradesPerDay) return "SKIP_DAILY_TRADE_LIMIT";
   if(pnl+OwnFloatingProfit()<=-AccountInfoDouble(ACCOUNT_BALANCE)*MaxDailyLossPercent/100.0) return "SKIP_DAILY_LOSS";
   int bars_since_exit=last_exit>0?iBarShift(_Symbol,SignalTimeframe,last_exit,false):INT_MAX;
   if(last_exit>0 && bars_since_exit<TradeCooldownBars) return "SKIP_COOLDOWN";
   if(losses>=MaxConsecutiveLosses && bars_since_exit<LossCooldownBars) return "SKIP_CONSECUTIVE_LOSSES";
   return "";
}

void ManagePosition()
{
   double atr;
   if(!Value(atr_handle,0,0,atr) || atr<=0) return;
   MqlTick tick; if(!SymbolInfoTick(_Symbol,tick)) return;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=MagicNumber) continue;
      ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double open=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      double price=type==POSITION_TYPE_BUY?tick.bid:tick.ask;
      double initial_risk=MathAbs(tp-open)/MinRR;
      if(initial_risk<=0) continue;
      double candidate=sl;
      if(UseBreakEven && MathAbs(price-open)>=initial_risk*BreakEvenTriggerR)
      {
         double buffer=BreakEvenBufferPoints*SymbolInfoDouble(_Symbol,SYMBOL_POINT);
         double breakeven=open+(type==POSITION_TYPE_BUY?buffer:-buffer);
         if((type==POSITION_TYPE_BUY && (sl<breakeven || sl==0)) || (type==POSITION_TYPE_SELL && (sl>breakeven || sl==0))) candidate=breakeven;
      }
      if(UseTrailingStop && MathAbs(price-open)>=initial_risk)
      {
         double trailing=price+(type==POSITION_TYPE_BUY?-atr*TrailingATRMultiplier:atr*TrailingATRMultiplier);
         if(type==POSITION_TYPE_BUY) candidate=MathMax(candidate,trailing);
         else candidate=candidate==0?trailing:MathMin(candidate,trailing);
      }
      if(candidate!=sl && ((type==POSITION_TYPE_BUY && candidate<price) || (type==POSITION_TYPE_SELL && candidate>price)))
      {
         if(!trade.PositionModify(ticket,NormalizeDouble(candidate,_Digits),tp))
            Print("AURUM_MANAGE|MODIFY_REJECTED|",trade.ResultRetcodeDescription());
      }
   }
}

void ProcessBar()
{
   Setup setup; string skip;
   if(!BuildSetup(setup,skip))
   {
      string side=setup.direction>0?"BUY":setup.direction<0?"SELL":"NONE";
      LogSkip(skip,"candidate="+side+(setup.reasons==""?"":"|"+setup.reasons));
      return;
   }
   string direction=setup.direction>0?"BUY":"SELL";
   PriceLine("SL",setup.stop,clrTomato,STYLE_DASH);
   PriceLine("TP",setup.take,clrMediumSeaGreen,STYLE_DOT);
   string blocked=ExecutionBlock(iTime(_Symbol,SignalTimeframe,1),setup.direction);
   if(blocked!="") { LogSkip(blocked,direction+" score "+DoubleToString(setup.score,0)); return; }

   MqlTick tick; if(!SymbolInfoTick(_Symbol,tick)) { LogSkip("SKIP_TICK_UNAVAILABLE"); return; }
   double price=setup.direction>0?tick.ask:tick.bid;
   double minimum_stop=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   if(MathAbs(price-setup.stop)<minimum_stop || MathAbs(setup.take-price)<minimum_stop) { LogSkip("SKIP_BROKER_STOP_LEVEL"); return; }
   double live_risk=MathAbs(price-setup.stop);
   if(live_risk<=0 || live_risk>setup.atr*MaxSLATR) { LogSkip("SKIP_SL_TOO_WIDE"); return; }
   double live_rr=MathAbs(setup.take-price)/live_risk;
   if(live_rr<MinRR) { LogSkip("SKIP_RR_TOO_LOW",DoubleToString(live_rr,2)); return; }
   double volume;
   if(!CalculateVolume(setup,price,volume,skip)) { LogSkip(skip); return; }

   string comment=StringSubstr("AX2|"+direction+"|"+setup.reasons,0,31);
   bool sent=setup.direction>0
      ?trade.Buy(volume,_Symbol,0,NormalizeDouble(setup.stop,_Digits),NormalizeDouble(setup.take,_Digits),comment)
      :trade.Sell(volume,_Symbol,0,NormalizeDouble(setup.stop,_Digits),NormalizeDouble(setup.take,_Digits),comment);
   uint code=trade.ResultRetcode();
   bool filled=sent && (code==TRADE_RETCODE_DONE || code==TRADE_RETCODE_PLACED || code==TRADE_RETCODE_DONE_PARTIAL);
   if(!filled) { LogSkip("ORDER_REJECTED",IntegerToString((int)code)+" "+trade.ResultRetcodeDescription()); return; }
   string key="Aurum.LastBar."+IntegerToString((int)MagicNumber)+"."+_Symbol+"."+IntegerToString((int)SignalTimeframe);
   GlobalVariableSet(key,(double)iTime(_Symbol,SignalTimeframe,1));
   Print("AURUM_EXECUTE|",direction,"|volume=",DoubleToString(volume,2),"|score=",DoubleToString(setup.score,0),"|rr=",DoubleToString(live_rr,2),"|",setup.reasons);
   DrawPanel("EXECUTED "+direction+" "+DoubleToString(volume,2)+" lots | "+setup.reasons);
}

int OnInit()
{
   if(StructureLookback<12 || RiskPerTrade<=0 || RiskPerTrade>MaxRiskPerTrade || MaxRiskPerTrade>1.0 ||
      MinConfidence<70 || MinConfidence>100 || MinRR<1 || MinADX<0 || ATRPeriod<2 || ATRStopMultiplier<=0 ||
      MaxSLATR<=0 || MinATRNormalized<0 || MaxATRNormalized<=MinATRNormalized || FixedVolume<=0 ||
      SessionStartHour<0 || SessionStartHour>23 || SessionEndHour<0 || SessionEndHour>23 || MarginSafetyMultiple<1)
      return INIT_PARAMETERS_INCORRECT;
   ema20_handle=iMA(_Symbol,SignalTimeframe,20,0,MODE_EMA,PRICE_CLOSE);
   ema50_handle=iMA(_Symbol,SignalTimeframe,50,0,MODE_EMA,PRICE_CLOSE);
   ema200_handle=iMA(_Symbol,SignalTimeframe,200,0,MODE_EMA,PRICE_CLOSE);
   h1ema50_handle=iMA(_Symbol,TrendTimeframe,50,0,MODE_EMA,PRICE_CLOSE);
   h1ema200_handle=iMA(_Symbol,TrendTimeframe,200,0,MODE_EMA,PRICE_CLOSE);
   rsi_handle=iRSI(_Symbol,SignalTimeframe,14,PRICE_CLOSE);
   adx_handle=iADX(_Symbol,SignalTimeframe,14);
   atr_handle=iATR(_Symbol,SignalTimeframe,ATRPeriod);
   if(ema20_handle==INVALID_HANDLE || ema50_handle==INVALID_HANDLE || ema200_handle==INVALID_HANDLE ||
      h1ema50_handle==INVALID_HANDLE || h1ema200_handle==INVALID_HANDLE || rsi_handle==INVALID_HANDLE ||
      adx_handle==INVALID_HANDLE || atr_handle==INVALID_HANDLE) return INIT_FAILED;
   current_mode=StartupMode;
   if(current_mode==MODE_AUTO_DEMO && !IsDemoOrTester()) current_mode=MODE_MANUAL;
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(SlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   DrawPanel("Quality-first baseline; waiting for a closed candle");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   int handles[]={ema20_handle,ema50_handle,ema200_handle,h1ema50_handle,h1ema200_handle,rsi_handle,adx_handle,atr_handle};
   for(int i=0;i<ArraySize(handles);i++) if(handles[i]!=INVALID_HANDLE) IndicatorRelease(handles[i]);
   ObjectsDeleteAll(0,prefix);
}

void OnTick()
{
   ManagePosition();
   if(current_mode==MODE_PAUSED) return;
   datetime bar=iTime(_Symbol,SignalTimeframe,0);
   if(bar<=0 || bar==last_bar) return;
   last_bar=bar;
   ProcessBar();
}

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
{
   if(id!=CHARTEVENT_OBJECT_CLICK) return;
   if(sparam==prefix+"Auto")
   {
      if(!IsDemoOrTester()) { current_mode=MODE_MANUAL; DrawPanel("BLOCKED: Auto mode requires a Demo account"); }
      else { current_mode=MODE_AUTO_DEMO; DrawPanel("Auto Demo armed; waits for a new closed candle"); }
   }
   else if(sparam==prefix+"Manual") { current_mode=MODE_MANUAL; DrawPanel("Manual: analysis continues, no new EA orders"); }
   else if(sparam==prefix+"Pause") { current_mode=MODE_PAUSED; DrawPanel("Paused: no analysis and no new EA orders"); }
   if(StringFind(sparam,prefix)==0) ObjectSetInteger(0,sparam,OBJPROP_STATE,false);
}
