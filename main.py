# ============================================
# INSTALL
# ============================================



# ============================================
# IMPORT
# ============================================
import os

import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

from datetime import datetime, timedelta

from ta.momentum import RSIIndicator
from ta.trend import MACD


# ============================================
# CONFIG
# ============================================

GOAPI_KEY = os.getenv("GOAPI_KEY")

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

BASE_URL = os.getenv("BASE_URL", "https://api.goapi.io")


# ============================================
# GET LQ45 STOCKS
# ============================================

def get_trending_stocks():

    url = f"{BASE_URL}/stock/idx/index/LQ45/items"

    headers = {
        "accept": "application/json",
        "X-API-KEY": GOAPI_KEY
    }

    response = requests.get(url, headers=headers)

    print("STATUS:", response.status_code)

    data = response.json()

    print(data)

    # ============================================
    # FALLBACK
    # ============================================

    fallback = [
        "BBCA",
        "BBRI",
        "BMRI",
        "TLKM",
        "ASII",
        "ANTM",
        "ADRO",
        "UNTR",
        "ICBP",
        "INDF"
    ]

    # ============================================
    # VALIDATION
    # ============================================

    if 'data' not in data:

        print("ERROR API RESPONSE")

        return fallback

    if 'results' not in data['data']:

        print("RESULTS NOT FOUND")

        return fallback

    stocks = data['data']['results']

    # ============================================
    # LIMIT
    # ============================================

    stocks = stocks[:30]

    print("TOTAL STOCKS:", len(stocks))

    return stocks


# ============================================
# GET HISTORICAL DATA
# ============================================

def get_historical_data(symbol):

    today = datetime.today()

    from_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")

    to_date = today.strftime("%Y-%m-%d")

    url = f"{BASE_URL}/stock/idx/{symbol}/historical"

    headers = {
        "accept": "application/json",
        "X-API-KEY": GOAPI_KEY
    }

    params = {
        "from": from_date,
        "to": to_date
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    data = response.json()

    return data


# ============================================
# ANALYZE STOCK
# ============================================

def analyze_stock(symbol):

    try:

        # ============================================
        # YAHOO SYMBOL
        # ============================================

        yahoo_symbol = f"{symbol}.JK"

        # ============================================
        # DOWNLOAD DATA
        # ============================================

        df = yf.download(
            yahoo_symbol,
            period="3mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        # yfinance can return MultiIndex columns depending on version/config.
        # Flatten to a single level so each field lookup returns scalar values.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if len(df) < 30:
            return None

        # ============================================
        # CLOSE SERIES
        # ============================================

        close_series = df['Close'].squeeze()

        # ============================================
        # RSI
        # ============================================

        rsi = RSIIndicator(close=close_series)

        df['rsi'] = rsi.rsi()

        # ============================================
        # MACD
        # ============================================

        macd = MACD(close=close_series)

        df['macd'] = macd.macd()

        df['macd_signal'] = macd.macd_signal()

        # ============================================
        # INDICATORS
        # ============================================

        df['ema20'] = df['Close'].ewm(span=20).mean()

        df['ema50'] = df['Close'].ewm(span=50).mean()

        latest = df.iloc[-1].copy()

        prev = df.iloc[-2].copy()

        score = 0
        max_score = 10

        reasons = []

        # ============================================
        # 1. RSI HEALTHY
        # ============================================

        if 40 <= float(latest['rsi']) <= 65:
            score += 1
            reasons.append("RSI sehat")

        # ============================================
        # 2. RSI UP
        # ============================================

        if float(latest['rsi']) > float(prev['rsi']):
            score += 1
            reasons.append("RSI naik")

        # ============================================
        # 3. MACD BULLISH
        # ============================================

        if float(latest['macd']) > float(latest['macd_signal']):
            score += 1
            reasons.append("MACD bullish crossover")

        # ============================================
        # 4. MACD POSITIVE
        # ============================================

        if float(latest['macd']) > 0:
            score += 1
            reasons.append("MACD positif")

        # ============================================
        # 5. PRICE UP
        # ============================================

        if float(latest['Close']) > float(prev['Close']):
            score += 1
            reasons.append("Momentum harga naik")

        # ============================================
        # 6. EMA20 > EMA50
        # ============================================

        if float(latest['ema20']) > float(latest['ema50']):
            score += 1
            reasons.append("Trend bullish EMA")

        # ============================================
        # 7. CLOSE ABOVE EMA20
        # ============================================

        if float(latest['Close']) > float(latest['ema20']):
            score += 1
            reasons.append("Close di atas EMA20")

        # ============================================
        # 8. VOLUME ABOVE AVG
        # ============================================

        avg_volume = df['Volume'].mean()

        if float(latest['Volume']) > float(avg_volume):
            score += 1
            reasons.append("Volume di atas rata-rata")

        # ============================================
        # 9. BREAKOUT 20 DAY HIGH
        # ============================================

        highest_20 = df['High'].tail(20).max()

        if float(latest['Close']) >= float(highest_20):
            score += 1
            reasons.append("Breakout high 20 hari")

        # ============================================
        # 10. GREEN CANDLE
        # ============================================

        if float(latest['Close']) > float(latest['Open']):
            score += 1
            reasons.append("Bullish candle")

        # ============================================
        # SIGNAL
        # ============================================

        if score >= 8:
            signal = "STRONG BUY"

        elif score >= 6:
            signal = "BUY"

        elif score >= 4:
            signal = "HOLD"

        else:
            signal = "SELL"

        # ============================================
        # PRICE PLAN
        # ============================================

        current_price = float(latest['Close'])

        buy_price = current_price

        take_profit = buy_price * 1.05

        cut_loss = buy_price * 0.97

        rr_ratio = (
            (take_profit - buy_price)
            /
            (buy_price - cut_loss)
        )

        # ============================================
        # RESULT
        # ============================================

        return {

            "symbol": symbol,

            "price": round(current_price, 2),

            "rsi": round(float(latest['rsi']), 2),

            "macd": round(float(latest['macd']), 2),

            "signal": signal,

            "buy_price": round(buy_price, 2),

            "take_profit": round(take_profit, 2),

            "cut_loss": round(cut_loss, 2),

            "rr_ratio": round(rr_ratio, 2),

            "score": score,

            "max_score": max_score,

            "reasons": reasons
        }

    except Exception as e:

        print(f"ERROR {symbol}: {e}")

        return None



# ============================================
# MAIN SCANNER
# ============================================

print("===================================")
print("GET TRENDING STOCKS")
print("===================================")

stocks = get_trending_stocks()

print(stocks)

all_results = []

# ============================================
# ANALYZE ALL STOCKS
# ============================================

for stock in stocks:

    try:

        print(f"\nANALYZE {stock}")

        result = analyze_stock(stock)

        if result is not None:

            all_results.append(result)

            print(result)

    except Exception as e:

        print(f"ERROR {stock}: {e}")


# ============================================
# SORT BEST STOCKS
# ============================================

top_stocks = sorted(
    all_results,
    key=lambda x: (
        x['score'],
        x['rsi']
    ),
    reverse=True
)[:10]


# ============================================
# PRINT RESULTS
# ============================================

print("\n===================================")
print("TOP 10 STOCKS")
print("===================================")

for stock in top_stocks:

    print(stock)


# ============================================
# SEND DISCORD
# ============================================

def send_discord(top_stocks):

    now = datetime.now(
    ZoneInfo("Asia/Jakarta")
).strftime("%Y-%m-%d %H:%M:%S WIB")

    message = f"""
📊 TOP 10 STOCK PICKS
🕒 {now}
"""
    # LIMIT 10 STOCKS
    for idx, stock in enumerate(top_stocks[:10], start=1):

        emoji = "🟢"

        if stock['signal'] == "HOLD":
            emoji = "🟡"

        elif stock['signal'] == "SELL":
            emoji = "🔴"

        message += f"""
{emoji} #{idx} {stock['symbol']} ({stock['signal']})

💰 Price : {float(stock['price'])}

🎯 Buy Area : {float(stock['buy_price'])}
✅ Take Profit : {float(stock['take_profit'])}
🛑 Cut Loss : {float(stock['cut_loss'])}

📊 RSI : {float(stock['rsi'])}
⭐ Score : {int(stock['score'])}/{int(stock['max_score'])}
━━━━━━━━━━━━━━━━━━
"""

    payload = {
        "content": message[:1900]
    }

    response = requests.post(
        DISCORD_WEBHOOK,
        json=payload
    )

    print("DISCORD STATUS:", response.status_code)

    print(response.text)

# ============================================
# SEND TO DISCORD
# ============================================

print("\nSEND TO DISCORD...\n")

send_discord(top_stocks)
