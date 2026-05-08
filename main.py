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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange


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

        # ============================================
        # ATR FOR RISK CONTROL
        # ============================================
        atr_indicator = AverageTrueRange(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=14
        )
        df['atr'] = atr_indicator.average_true_range()

        latest = df.iloc[-1].copy()

        prev = df.iloc[-2].copy()

        score = 0
        max_score = 14

        reasons = []
        daily_change_pct = (
            (float(latest['Close']) - float(prev['Close']))
            / float(prev['Close'])
        ) * 100
        high_low_range_pct = (
            (float(latest['High']) - float(latest['Low']))
            / float(latest['Close'])
        ) * 100
        close_to_high_pct = (
            (float(latest['High']) - float(latest['Close']))
            / float(latest['Close'])
        ) * 100
        atr_pct = (float(latest['atr']) / float(latest['Close'])) * 100

        # ============================================
        # 1. RSI MOMENTUM HEALTHY (scalping ideal)
        # ============================================

        if 50 <= float(latest['rsi']) <= 68:
            score += 1
            reasons.append("RSI momentum sehat (50-68)")

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
        # 4. MACD HISTOGRAM MENGUAT
        # ============================================

        latest_hist = float(latest['macd']) - float(latest['macd_signal'])
        prev_hist = float(prev['macd']) - float(prev['macd_signal'])
        if latest_hist > prev_hist:
            score += 1
            reasons.append("Histogram MACD menguat")

        # ============================================
        # 5. MOMENTUM HARIAN POSITIF
        # ============================================

        if daily_change_pct >= 0.8:
            score += 1
            reasons.append(f"Momentum harian kuat ({daily_change_pct:.2f}%)")

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
        # 8. VOLUME SURGE VS RATA-RATA 20 HARI
        # ============================================

        avg_volume = df['Volume'].tail(20).mean()
        volume_ratio = float(latest['Volume']) / float(avg_volume) if float(avg_volume) > 0 else 0

        if volume_ratio >= 1.3:
            score += 1
            reasons.append(f"Volume surge {volume_ratio:.2f}x")

        # ============================================
        # 9. BREAKOUT HIGH 10 HARI (lebih agresif untuk scalping)
        # ============================================

        prev_highest_10 = df['High'].iloc[-11:-1].max()

        if float(latest['Close']) > float(prev_highest_10):
            score += 1
            reasons.append("Breakout high 10 hari")

        # ============================================
        # 10. GREEN CANDLE
        # ============================================

        if float(latest['Close']) > float(latest['Open']):
            score += 1
            reasons.append("Bullish candle")

        # ============================================
        # 11. CLOSE DEKAT HIGH (tekanan beli masih kuat)
        # ============================================

        if close_to_high_pct <= 1.0:
            score += 1
            reasons.append("Close dekat high harian")

        # ============================================
        # 12. RANGE CUKUP UNTUK SCALPING
        # ============================================

        if high_low_range_pct >= 1.5:
            score += 1
            reasons.append(f"Range harian menarik ({high_low_range_pct:.2f}%)")

        # ============================================
        # 13. VOLATILITY TERKONTROL (LOW RISK)
        # ============================================

        if atr_pct <= 3.2:
            score += 1
            reasons.append(f"ATR terkendali ({atr_pct:.2f}%)")

        # ============================================
        # 14. TIDAK TERLALU OVEREXTENDED
        # ============================================

        if daily_change_pct <= 3.5 and float(latest['rsi']) < 72:
            score += 1
            reasons.append("Belum overextended")

        # ============================================
        # SIGNAL
        # ============================================

        if score >= 12:
            signal = "STRONG BUY"

        elif score >= 10:
            signal = "BUY"

        elif score >= 8:
            signal = "HOLD"

        else:
            signal = "SELL"

        # ============================================
        # PRICE PLAN
        # ============================================

        current_price = float(latest['Close'])

        buy_area_low = min(float(latest['ema20']), current_price * 0.995)
        buy_area_high = current_price * 1.003
        buy_price = (buy_area_low + buy_area_high) / 2

        take_profit = current_price * 1.025

        cut_loss = buy_area_low * 0.985

        rr_ratio = (
            (take_profit - buy_price)
            /
            (buy_price - cut_loss)
        )

        # ============================================
        # HARD RISK FILTER
        # ============================================

        if (
            float(latest['rsi']) >= 75
            or daily_change_pct > 5.0
            or atr_pct > 4.5
            or volume_ratio < 1.1
            or rr_ratio < 1.3
        ):
            return None

        # ============================================
        # RESULT
        # ============================================

        return {

            "symbol": symbol,

            "price": round(current_price, 2),

            "rsi": round(float(latest['rsi']), 2),

            "macd": round(float(latest['macd']), 2),

            "signal": signal,

            "buy_area_low": round(buy_area_low, 2),

            "buy_area_high": round(buy_area_high, 2),

            "buy_price": round(buy_price, 2),

            "take_profit": round(take_profit, 2),

            "cut_loss": round(cut_loss, 2),

            "rr_ratio": round(rr_ratio, 2),

            "score": score,

            "max_score": max_score,

            "daily_change_pct": round(daily_change_pct, 2),

            "volume_ratio": round(volume_ratio, 2),

            "atr_pct": round(atr_pct, 2),

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

ranked_stocks = sorted(
    all_results,
    key=lambda x: (
        x['score'],
        x['daily_change_pct'],
        x['rsi']
    ),
    reverse=True
)

top_stocks = [
    s for s in ranked_stocks
    if s['signal'] in ["BUY", "STRONG BUY"]
][:5]


# ============================================
# PRINT RESULTS
# ============================================

print("\n===================================")
print("TOP 5 STOCKS (SCALPING HARIAN)")
print("===================================")

for stock in top_stocks:

    print(stock)


# ============================================
# SEND DISCORD
# ============================================

def send_discord(top_stocks, ranked_stocks):

    now = datetime.now(
    ZoneInfo("Asia/Jakarta")
).strftime("%Y-%m-%d %H:%M:%S WIB")

    message = f"""
📊 TOP 5 SAHAM SCALPING (HARIAN)
🕒 {now}
🎯 Fokus: momentum cepat, volume, breakout
🛡️ Mode: low-risk filter aktif
"""
    stocks_to_send = top_stocks[:5]
    warning = ""

    using_fallback = False
    if len(stocks_to_send) == 0:
        using_fallback = True
        warning = "\n⚠️ Tidak ada kandidat BUY yang lolos filter. Mode defensif aktif."
        stocks_to_send = ranked_stocks[:3]

    message += warning

    # LIMIT 5 STOCKS (fallback 3 HOLD/SELL terbaik jika BUY kosong)
    for idx, stock in enumerate(stocks_to_send, start=1):

        emoji = "🟢"

        if stock['signal'] == "HOLD":
            emoji = "🟡"

        elif stock['signal'] == "SELL":
            emoji = "🔴"

        reason_text = ", ".join(stock['reasons'][:4])
        signal_label = stock['signal']
        if using_fallback:
            signal_label = f"WATCHLIST-{stock['signal']}"

        message += f"""
{emoji} #{idx} {stock['symbol']} ({signal_label})

💰 Last Price : {float(stock['price'])}
📈 Change 1D : {float(stock['daily_change_pct'])}%
🔊 Volume : {float(stock['volume_ratio'])}x rata-rata 20H
⚡ ATR : {float(stock['atr_pct'])}%

🎯 Buy Area : {float(stock['buy_area_low'])} - {float(stock['buy_area_high'])}
✅ Take Profit : {float(stock['take_profit'])}
🛑 Cut Loss : {float(stock['cut_loss'])}
⚖️ R/R : {float(stock['rr_ratio'])}

📊 RSI : {float(stock['rsi'])}
⭐ Score : {int(stock['score'])}/{int(stock['max_score'])}
🧠 Alasan : {reason_text}
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

send_discord(top_stocks, ranked_stocks)
