import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="IA CSP Scanner - Tradier", layout="wide")

# =============================
# STREAMLIT SECRET REQUIRED
# =============================
# In Streamlit Secrets add:
# TRADIER_TOKEN = "your_token_here"

TOKEN = st.secrets.get("TRADIER_TOKEN", "")

WATCHLIST = [
    "NVDA", "ALAB", "AVGO", "MRVL", "AMD", "MU", "ASML", "TSM", "ANET",
    "GOOGL", "META", "MSFT", "AMZN", "PLTR", "CRM",
    "MSTR", "IBIT", "COIN", "GLXY", "CRCL",
    "RKLB", "ASTS", "ARM",
    "EOSE", "CPER", "SLV",
    "HOOD", "SOFI",
    "NBIS", "INFQ", "NVTS", "IREN",
    "TSLA"
]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

def tradier_get(endpoint, params=None):

    if not TOKEN:
        raise Exception("Missing TRADIER_TOKEN")

    url = f"https://api.tradier.com/v1{endpoint}"

    response = requests.get(
        url,
        headers=HEADERS,
        params=params or {},
        timeout=20
    )

    if response.status_code != 200:
        raise Exception(
            f"Tradier API Error {response.status_code}: {response.text[:200]}"
        )

    return response.json()

def as_list(value):

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]

def safe_float(value, default=0):

    try:
        if value is None or value == "":
            return default
        return float(value)
    except:
        return default

def get_quote(symbol):

    data = tradier_get(
        "/markets/quotes",
        {"symbols": symbol}
    )

    quote = data.get("quotes", {}).get("quote")

    if isinstance(quote, list):
        quote = quote[0]

    if not quote:
        raise Exception(f"No quote for {symbol}")

    price = safe_float(
        quote.get("last") or quote.get("close")
    )

    if price <= 0:
        raise Exception(f"No valid price for {symbol}")

    return price

def get_expirations(symbol):

    data = tradier_get(
        "/markets/options/expirations",
        {
            "symbol": symbol,
            "includeAllRoots": "true"
        }
    )

    dates = data.get("expirations", {}).get("date")

    dates = as_list(dates)

    if not dates:
        raise Exception(f"No expirations for {symbol}")

    return dates

def get_chain(symbol, expiration):

    data = tradier_get(
        "/markets/options/chains",
        {
            "symbol": symbol,
            "expiration": expiration,
            "greeks": "true"
        }
    )

    options = data.get("options", {}).get("option")

    options = as_list(options)

    if not options:
        return pd.DataFrame()

    return pd.DataFrame(options)

def monthly_roi(mid, strike, dte):

    if strike <= 0 or dte <= 0:
        return 0

    return (mid / strike) * (30 / dte) * 100

def get_greek_value(greeks, key):

    if isinstance(greeks, dict):
        return safe_float(greeks.get(key), 0)

    return 0

st.title("💰 IA CSP Scanner - Tradier")

st.caption(
    "Scans IA-style watchlist for CSP candidates. "
    "Research tool only."
)

if not TOKEN:

    st.error(
        "Missing TRADIER_TOKEN in Streamlit Secrets."
    )

    st.stop()

with st.sidebar:

    st.header("Scanner Settings")

    max_tickers = st.slider(
        "Tickers to scan",
        1,
        len(WATCHLIST),
        5
    )

    min_dte = st.slider(
        "Minimum DTE",
        1,
        90,
        28
    )

    max_dte = st.slider(
        "Maximum DTE",
        min_dte,
        120,
        45
    )

    target_roi = st.slider(
        "Target monthly ROI %",
        0.5,
        10.0,
        5.0,
        0.25
    )

    target_sd = st.slider(
        "Target SD distance",
        1.0,
        3.0,
        2.0,
        0.25
    )

selected_tickers = WATCHLIST[:max_tickers]

st.write(
    "**Selected tickers:**",
    ", ".join(selected_tickers)
)

if st.button("Run CSP Scan", type="primary"):

    results = []
    errors = []

    progress = st.progress(0)

    for i, symbol in enumerate(selected_tickers):

        try:

            price = get_quote(symbol)

            expirations = get_expirations(symbol)

            for exp in expirations:

                try:

                    dte = (
                        datetime.strptime(
                            exp,
                            "%Y-%m-%d"
                        ).date()
                        -
                        datetime.now().date()
                    ).days

                except:
                    continue

                if dte < min_dte or dte > max_dte:
                    continue

                chain = get_chain(symbol, exp)

                if chain.empty:
                    continue

                if "option_type" not in chain.columns:

                    errors.append({
                        "Ticker": symbol,
                        "Error": f"No option_type column for {exp}"
                    })

                    continue

                puts = chain[
                    chain["option_type"]
                    .astype(str)
                    .str.lower()
                    == "put"
                ]

                for _, row in puts.iterrows():

                    strike = safe_float(row.get("strike"))

                    bid = safe_float(row.get("bid"))

                    ask = safe_float(row.get("ask"))

                    last = safe_float(row.get("last"))

                    if strike <= 0:
                        continue

                    if bid > 0 and ask > 0 and ask >= bid:
                        mid = (bid + ask) / 2

                    elif last > 0:
                        mid = last

                    else:
                        continue

                    greeks = row.get("greeks", {})

                    delta = abs(
                        get_greek_value(
                            greeks,
                            "delta"
                        )
                    )

                    iv = get_greek_value(
                        greeks,
                        "mid_iv"
                    )

                    if iv <= 0:

                        iv = get_greek_value(
                            greeks,
                            "smv_vol"
                        )

                    if iv > 5:
                        iv = iv / 100

                    if iv <= 0:
                        continue

                    expected_move = (
                        price
                        * iv
                        * np.sqrt(dte / 365)
                    )

                    if expected_move <= 0:
                        continue

                    sd_distance = (
                        (price - strike)
                        / expected_move
                    )

                    roi = monthly_roi(
                        mid,
                        strike,
                        dte
                    )

                    score = 0
                    reasons = []

                    if roi >= target_roi:
                        score += 25
                        reasons.append("ROI target met")

                    if sd_distance >= target_sd:
                        score += 25
                        reasons.append("2SD away")

                    if 0.10 <= delta <= 0.30:
                        score += 20
                        reasons.append("Good delta")

                    oi = safe_float(
                        row.get("open_interest")
                    )

                    if oi >= 100:
                        score += 15
                        reasons.append("Good OI")

                    spread = (
                        ((ask - bid) / mid) * 100
                        if bid > 0 and ask > 0 and mid > 0
                        else 999
                    )

                    if spread <= 25:
                        score += 15
                        reasons.append("Spread okay")

                    if score >= 75:
                        action = "BEST"

                    elif score >= 55:
                        action = "WATCH"

                    else:
                        action = "AVOID"

                    results.append({

                        "Ticker": symbol,
                        "Action": action,
                        "Score": round(score, 1),

                        "Price": round(price, 2),

                        "Expiration": exp,

                        "DTE": dte,

                        "Strike": strike,

                        "Bid": bid,

                        "Ask": ask,

                        "Premium": round(mid * 100, 2),

                        "Monthly ROI %": round(roi, 2),

                        "SD Distance": round(sd_distance, 2),

                        "Delta": round(delta, 3),

                        "IV %": round(iv * 100, 2),

                        "Open Interest": int(oi),

                        "Spread %": round(spread, 2),

                        "Notes": "; ".join(reasons)
                    })
if results:

    df = pd.DataFrame(results)

    df = df.sort_values(
        by=[
            "Ticker",
            "Score",
            "Monthly ROI %",
            "SD Distance"
        ],
        ascending=[True, False, False, False]
    )

    # Keep ONLY best contract per ticker
    df = df.groupby("Ticker").head(1).reset_index(drop=True)
        except Exception as e:

            errors.append({
                "Ticker": symbol,
                "Error": str(e)
            })

        progress.progress(
            (i + 1) / len(selected_tickers)
        )

    if results:


        st.subheader("CSP Scan Results")

        st.dataframe(
            df,
            use_container_width=True,
            height=600
        )

        csv = df.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download CSV",
            csv,
            "csp_scan.csv",
            "text/csv"
        )

    else:

        st.error(
            "No CSP candidates found."
        )

    if errors:

        st.subheader("Debug / Errors")

        st.dataframe(
            pd.DataFrame(errors),
            use_container_width=True
        )

                    
                        
            
