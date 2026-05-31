import yfinance as yf
import pandas as pd
import numpy as np
import talib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== CONFIG ==================
TIMEFRAME = '15m'
PERIOD = '7d'
TOKEN = os.getenv("TELEGRAM_TOKEN")

def get_yf_symbol(pair):
    pair = pair.upper().replace('/', '').replace(' ', '')
    if pair in ['XAU', 'XAUUSD', 'GOLD']:
        return 'GC=F'
    if pair in ['XAG', 'XAGUSD', 'SILVER']:
        return 'SI=F'
    return f"{pair}=X"

def fetch_data(pair):
    symbol = get_yf_symbol(pair)
    df = yf.download(symbol, period=PERIOD, interval=TIMEFRAME, progress=False)
    df = df.reset_index().rename(columns={'Datetime':'timestamp','Open':'open','High':'high',
                                          'Low':'low','Close':'close','Volume':'volume'})
    return df, pair.upper()

def detect_all_patterns(df):
    patterns = {}
    high = df['high'].rolling(50).max().iloc[-1]
    low = df['low'].rolling(50).min().iloc[-1]
    diff = high - low
    patterns['Fib_Levels'] = {k: round(high - v*diff, 5) for k,v in {'0':0,'0.236':0.236,'0.382':0.382,'0.5':0.5,'0.618':0.618,'1':1}.items()}
    
    df['swing_high'] = df['high'].rolling(5).max()
    df['swing_low'] = df['low'].rolling(5).min()
    patterns['BOS_Up'] = bool(df['close'].iloc[-1] > df['swing_high'].shift(1).iloc[-1])
    patterns['CHOCH_Down'] = bool(df['close'].iloc[-1] < df['swing_low'].shift(1).iloc[-1])
    
    patterns['Hammer'] = talib.CDLHAMMER(df['open'],df['high'],df['low'],df['close']).iloc[-1] != 0
    patterns['Engulfing'] = talib.CDLENGULFING(df['open'],df['high'],df['low'],df['close']).iloc[-1] != 0
    
    df['rsi'] = talib.RSI(df['close'], 14)
    df['ema20'] = talib.EMA(df['close'], 20)
    df['ema50'] = talib.EMA(df['close'], 50)
    patterns['RSI'] = round(df['rsi'].iloc[-1], 2)
    patterns['Trend'] = "BULLISH" if df['close'].iloc[-1] > df['ema20'].iloc[-1] else "BEARISH"
    patterns['Volume_Spike'] = bool(df['volume'].iloc[-1] > df['volume'].rolling(20).mean().iloc[-1] * 1.5)
    
    return patterns, df

def create_chart(df, pair):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close']), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema20'], name="EMA20", line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema50'], name="EMA50", line=dict(color='blue')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['rsi'], name="RSI", line=dict(color='purple')), row=2, col=1)
    fig.update_layout(title=f"{pair} Analysis", height=700)
    path = f"{pair}_chart.png"
    fig.write_image(path)
    return path

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /analyze EURUSD or /analyze XAU")
        return
    pair = context.args[0]
    msg = await update.message.reply_text(f"🔍 Analyzing {pair}...")
    try:
        df, name = fetch_data(pair)
        patterns, _ = detect_all_patterns(df)
        price = df['close'].iloc[-1]
        score = 0
        if patterns['BOS_Up']: score += 25
        if patterns['CHOCH_Down']: score += 25
        if patterns.get('Hammer'): score += 10
        if patterns['Volume_Spike']: score += 10
        if patterns['RSI'] < 30: score += 15
        
        text = f"""
📊 **{name} ANALYSIS**
💰 Price: **{price:.5f}**
📈 Trend: **{patterns['Trend']}**
🔥 Score: **{score}/100**
        """
        await msg.edit_text(text)
        
        chart_path = create_chart(df, name)
        await update.message.reply_photo(photo=open(chart_path, 'rb'))
        os.remove(chart_path)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("analyze", analyze))
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
