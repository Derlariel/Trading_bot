#property copyright "Trading Bot"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

input string SignalFile = "TradingBot\\signal.csv";
input int RefreshSeconds = 5;
input color BuyColor = clrLimeGreen;
input color SellColor = clrTomato;
input color SupportColor = clrSeaGreen;
input color ResistanceColor = clrFireBrick;

string Prefix = "TradingBotOverlay_";

void RemoveObjects()
{
   ObjectsDeleteAll(0, Prefix);
}

void Line(string name, double price, color line_color, ENUM_LINE_STYLE style)
{
   if(price <= 0) return;
   name = Prefix + name;
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, line_color);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

void Zone(string name, double low, double high, color zone_color)
{
   if(low <= 0 || high < low) return;
   name = Prefix + name;
   datetime left = iTime(_Symbol, _Period, MathMin(Bars(_Symbol, _Period) - 1, 200));
   datetime right = TimeCurrent() + PeriodSeconds(_Period) * 50;
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, left, low, right, high);
   ObjectMove(0, name, 0, left, low);
   ObjectMove(0, name, 1, right, high);
   ObjectSetInteger(0, name, OBJPROP_COLOR, ColorToARGB(zone_color, 45));
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

void Status(string text, color text_color)
{
   string name = Prefix + "Status";
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, name, OBJPROP_COLOR, text_color);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 10);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

void Arrow(string signal, double price)
{
   string name = Prefix + "Signal";
   if(signal == "WAIT")
   {
      ObjectDelete(0, name);
      return;
   }
   bool buy = StringFind(signal, "BUY") >= 0;
   ENUM_OBJECT type = buy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL;
   if(ObjectFind(0, name) >= 0 && ObjectGetInteger(0, name, OBJPROP_TYPE) != type)
      ObjectDelete(0, name);
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, type, 0, iTime(_Symbol, _Period, 0), price);
   ObjectMove(0, name, 0, iTime(_Symbol, _Period, 0), price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, buy ? BuyColor : SellColor);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

void RefreshOverlay()
{
   int file = FileOpen(SignalFile, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ';');
   if(file == INVALID_HANDLE)
   {
      Status("Trading Bot: waiting for Python signal", clrSilver);
      return;
   }

   int version = (int)FileReadNumber(file);
   string symbol = FileReadString(file);
   string timeframe = FileReadString(file);
   string mode = FileReadString(file);
   datetime generated = (datetime)FileReadNumber(file);
   string signal = FileReadString(file);
   double confidence = FileReadNumber(file);
   double entry_low = FileReadNumber(file), entry_high = FileReadNumber(file);
   double stop = FileReadNumber(file), tp1 = FileReadNumber(file);
   double tp2 = FileReadNumber(file), tp3 = FileReadNumber(file);
   double support_low = FileReadNumber(file), support_high = FileReadNumber(file);
   double resistance_low = FileReadNumber(file), resistance_high = FileReadNumber(file);
   double rr = FileReadNumber(file);
   string decision = FileReadString(file), reason = FileReadString(file);
   FileClose(file);

   if(version != 2 || symbol != _Symbol)
   {
      RemoveObjects();
      Status("Trading Bot: signal is for " + symbol, clrSilver);
      return;
   }

   bool buy = StringFind(signal, "BUY") >= 0;
   color signal_color = signal == "WAIT" ? clrSilver : (buy ? BuyColor : SellColor);
   Zone("Support", support_low, support_high, SupportColor);
   Zone("Resistance", resistance_low, resistance_high, ResistanceColor);
   if(signal != "WAIT")
   {
      Zone("Entry", entry_low, entry_high, signal_color);
      Line("SL", stop, SellColor, STYLE_DASH);
      Line("TP1", tp1, BuyColor, STYLE_DOT);
      Line("TP2", tp2, BuyColor, STYLE_DOT);
      Line("TP3", tp3, BuyColor, STYLE_DOT);
      Arrow(signal, (entry_low + entry_high) / 2.0);
   }
   else
   {
      ObjectDelete(0, Prefix + "Entry");
      ObjectDelete(0, Prefix + "SL");
      ObjectDelete(0, Prefix + "TP1");
      ObjectDelete(0, Prefix + "TP2");
      ObjectDelete(0, Prefix + "TP3");
      Arrow(signal, 0);
   }
   string status = "Trading Bot | " + mode + " | " + signal + " | " + DoubleToString(confidence, 1) + "% | RR " + DoubleToString(rr, 2) + " | " + timeframe + " | " + TimeToString(generated);
   if(decision == "SKIP" && reason != "NO_TRADE_SIGNAL") status += " | BLOCKED: " + reason;
   Status(status, signal_color);
   ChartRedraw();
}

int OnInit()
{
   EventSetTimer(MathMax(1, RefreshSeconds));
   RefreshOverlay();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   RemoveObjects();
}

void OnTimer()
{
   RefreshOverlay();
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[],
                const double &close[], const long &tick_volume[], const long &volume[],
                const int &spread[])
{
   return rates_total;
}
