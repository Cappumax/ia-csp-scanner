
# ==========================================
# IA CSP SCANNER V3 - TRADIER
# ==========================================

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import math

st.set_page_config(
    page_title="IA CSP Scanner V3",
    layout="wide"
)

# ==========================================
# CONFIG
# ==========================================

TOKEN = st.secrets.get("TRADIER_TOKEN", "")

WATCHLIST = [
    "NVDA","ALAB","AVGO","MRVL","AMD","MU","ASML","TSM",
    "ANET","GOOGL","META","MSFT","AMZN","PLTR","CRM",
    "MSTR","IBIT","COIN","GLXY","CRCL",
    "RKLB","ASTS","ARM","EOSE","CPER","SLV",
    "HOOD","SOFI","NBIS","INFQ","NVTS","IREN","TSLA"
]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

# ==========================================
# HELPERS
# ==========================================

def tradier_get(endpoint, params=None):

    url = f"https://api.tradier.com/v1{endpoint}"

    response = requests.get(
        url,
        headers=HEADERS,
        params=params or {},
        timeout=20
    )

    if response.status_code != 200:
        raise Exception(f"Tradier Error {response.status_code}")

    return response.json()

def safe_float(x, default=0):

    try:
        if x is None:
            return default
        return float(x)
    except:
        return default

def as_list(x):

    if x is None:
        return []

    if isinstance(x, list):
        return x

    return [x]

# ==========================================
# DATA FUNCTIONS
# ==========================================

def get_quote(symbol):

    data = tradier_get(
        "/markets/quotes",
        {"symbols": symbol}
    )

    quote = data["quotes"]["quote"]

    return safe_float(quote["last"])

def get_history(symbol):

    try:

        data = tradier_get(
            "/markets/history",
            {
                "symbol": symbol,
                "interval": "daily",
                "start": "2025-01-01",
                "end": datetime.now().strftime("%Y-%m-%d")
            }
        )

        history = as_list(data["history"]["day"])

        closes = [
            safe_float(x["close"])
            for x in history
        ]

        return closes

    except:
        return []

def get_rsi(closes, period=14):

    if len(closes) < period + 1:
        return 50

    deltas = np.diff(closes)

    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return round(100 - (100 / (1 + rs)), 2)

def get_trend(closes):

    if len(closes) < 200:
        return "UNKNOWN"

    sma50 = np.mean(closes[-50:])
    sma200 = np.mean(closes[-200:])

    if sma50 > sma200:
        return "BULLISH"

    return "BEARISH"

def get_expirations(symbol):

    data = tradier_get(
        "/markets/options/expirations",
        {
            "symbol": symbol,
            "includeAllRoots": "true",
            "strikes": "false"
        }
    )

    return as_list(data["expirations"]["date"])

def get_chain(symbol, expiration):

    data = tradier_get(
        "/markets/options/chains",
        {
            "symbol": symbol,
            "expiration": expiration,
            "greeks": "true"
        }
    )

    return as_list(data["options"]["option"])

# ==========================================
# SIDEBAR
# ==========================================

st.title("💰 IA CSP Scanner V3")

st.sidebar.header("Scanner Settings")

max_tickers = st.sidebar.slider(
    "Tickers to scan",
    1,
    len(WATCHLIST),
    20
)

min_dte = st.sidebar.slider(
    "Minimum DTE",
    7,
    90,
    30
)

max_dte = st.sidebar.slider(
    "Maximum DTE",
    7,
    120,
    45
)

target_roi = st.sidebar.slider(
    "Target Monthly ROI %",
    0.5,
    10.0,
    2.0
)

target_sd = st.sidebar.slider(
    "Target SD Distance",
    0.5,
    5.0,
    2.0
)

st.sidebar.subheader("Delta Filter")

delta_filter = st.sidebar.checkbox(
    "Use Delta Filter",
    value=True
)

min_delta = st.sidebar.slider(
    "Minimum Delta",
    0.01,
    0.50,
    0.15,
    0.01
)

max_delta = st.sidebar.slider(
    "Maximum Delta",
    0.01,
    0.50,
    0.25,
    0.01
)

premium_filter = st.sidebar.checkbox(
    "Premium over $300 only",
    value=False
)

trend_filter = st.sidebar.checkbox(
    "Bullish Trend Only",
    value=False
)

best_only = st.sidebar.checkbox(
    "Only BEST setups",
    value=True
)

best_per_ticker = st.sidebar.checkbox(
    "Only best contract per ticker",
    value=True
)

selected_tickers = WATCHLIST[:max_tickers]

st.write(
    "**Selected tickers:**",
    ", ".join(selected_tickers)
)

# ==========================================
# SCAN
# ==========================================

if st.button("Run CSP Scan", type="primary"):

    results = []
    errors = []

    progress = st.progress(0)

    for i, symbol in enumerate(selected_tickers):

        try:

            price = get_quote(symbol)

            closes = get_history(symbol)

            rsi = get_rsi(closes)

            trend = get_trend(closes)

            expirations = get_expirations(symbol)

            for exp in expirations:

                dte = (
                    datetime.strptime(exp, "%Y-%m-%d")
                    - datetime.now()
                ).days

                if dte < min_dte or dte > max_dte:
                    continue

                chain = get_chain(symbol, exp)

                for option in chain:

                    if option.get("option_type") != "put":
                        continue

                    strike = safe_float(option.get("strike"))

                    if strike >= price:
                        continue

                    bid = safe_float(option.get("bid"))
                    ask = safe_float(option.get("ask"))
                    mid = round((bid + ask) / 2, 2)

                    if mid <= 0:
                        continue

                    greeks = option.get("greeks", {})

                    delta = abs(
                        safe_float(greeks.get("delta"))
                    )

                    iv = safe_float(
                        greeks.get("mid_iv")
                    )

                    volume = safe_float(option.get("volume"))
                    oi = safe_float(option.get("open_interest"))

                    premium = round(mid * 100, 2)

                    monthly_roi = round(
                        ((premium / (strike * 100)) * (30 / dte)) * 100,
                        2
                    )

                    annual_yield = round(
                        monthly_roi * 12,
                        2
                    )

                    prob_otm = round(
                        (1 - delta) * 100,
                        1
                    )

                    spread = round(
                        ((ask - bid) / ask) * 100,
                        2
                    ) if ask > 0 else 0

                    iv_rank = round(
                        iv * 100,
                        1
                    )

                    assignment_risk = "LOW"

                    if delta > 0.30:
                        assignment_risk = "HIGH"

                    elif delta > 0.20:
                        assignment_risk = "MED"

                    score = 0

                    if monthly_roi >= target_roi:
                        score += 2

                    if delta <= 0.25:
                        score += 2

                    if prob_otm >= 75:
                        score += 2

                    if trend == "BULLISH":
                        score += 2

                    if rsi < 70:
                        score += 1

                    if spread < 10:
                        score += 1

                    action = "PASS"

                    if score >= 8:
                        action = "BEST"

                    elif score >= 6:
                        action = "WATCH"

                    commentary = []

                    if trend == "BULLISH":
                        commentary.append("Bull trend")

                    if rsi > 70:
                        commentary.append("Overbought")

                    if prob_otm > 80:
                        commentary.append("High safety")

                    if spread > 15:
                        commentary.append("Wide spread")

                    if delta_filter:
                        if delta < min_delta or delta > max_delta:
                            continue

                    if premium_filter:
                        if premium < 300:
                            continue

                    if trend_filter:
                        if trend != "BULLISH":
                            continue

                    results.append({

                        "Ticker": symbol,
                        "Price": round(price, 2),
                        "Strike": strike,
                        "Expiration": exp,
                        "DTE": dte,
                        "Premium": premium,
                        "Monthly ROI %": monthly_roi,
                        "Annualized Yield %": annual_yield,
                        "Delta": round(delta, 2),
                        "Probability OTM %": prob_otm,
                        "IV %": round(iv * 100, 2),
                        "IV Rank": iv_rank,
                        "RSI": rsi,
                        "Trend": trend,
                        "Volume": int(volume),
                        "Open Interest": int(oi),
                        "Spread %": spread,
                        "Assignment Risk": assignment_risk,
                        "Score": score,
                        "Action": action,
                        "AI Commentary": ", ".join(commentary)

                    })

        except Exception as e:

            errors.append({
                "Ticker": symbol,
                "Error": str(e)
            })

        progress.progress(
            (i + 1) / len(selected_tickers)
        )

    # ==========================================
    # RESULTS
    # ==========================================

    if results:

        df = pd.DataFrame(results)

        if best_only:
            df = df[
                df["Action"].isin(["BEST", "WATCH"])
            ]

        if not df.empty:

            df = df.sort_values(
                by=[
                    "Annualized Yield %",
                    "Score"
                ],
                ascending=[False, False]
            )

            if best_per_ticker:

                df = (
                    df.groupby("Ticker")
                    .head(1)
                    .reset_index(drop=True)
                )

            
               st.subheader("CSP Scan Results")

              st.dataframe(
                df,
                use_container_width=True,
                height=700
              )

            csv = df.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download CSV",
                csv,
                "ia_csp_scan.csv",
                "text/csv"
        )

        else:

            st.warning("No setups matched filters.")

    else:

        st.error("No CSP setups found.")

    if errors:

        st.subheader("Errors / Debug")

        st.dataframe(
            pd.DataFrame(errors),
            use_container_width=True
        )
