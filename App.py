# REPLACE YOUR ENTIRE app.py WITH THIS FILE
# IA CSP Scanner - Tradier Version

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="IA CSP Scanner", layout="wide")

TOKEN = st.secrets["TRADIER_TOKEN"]

WATCHLIST = [
    "NVDA","ALAB","AVGO","MRVL","AMD","MU","ASML","TSM","ANET",
    "GOOGL","META","MSFT","AMZN","PLTR","CRM",
    "MSTR","IBIT","COIN","RKLB","ASTS","ARM",
    "HOOD","SOFI","IREN","TSLA"
]

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

def get_quote(symbol):
    url = "https://api.tradier.com/v1/markets/quotes"
    r = requests.get(url, headers=headers, params={"symbols": symbol})
    data = r.json()
    return data["quotes"]["quote"]

def get_expirations(symbol):
    url = "https://api.tradier.com/v1/markets/options/expirations"
    r = requests.get(url, headers=headers, params={"symbol": symbol})
    data = r.json()
    dates = data["expirations"]["date"]
    if isinstance(dates, str):
        dates = [dates]
    return dates

def get_chain(symbol, expiration):
    url = "https://api.tradier.com/v1/markets/options/chains"
    r = requests.get(
        url,
        headers=headers,
        params={
            "symbol": symbol,
            "expiration": expiration,
            "greeks": "true"
        }
    )
    data = r.json()
    options = data["options"]["option"]

    if isinstance(options, dict):
        options = [options]

    return pd.DataFrame(options)

def monthly_roi(mid, strike, dte):
    return (mid / strike) * (30 / dte) * 100

st.title("💰 IA CSP Scanner - Tradier")

max_tickers = st.slider("Tickers to scan", 1, len(WATCHLIST), 5)

if st.button("Run CSP Scan"):

    results = []

    tickers = WATCHLIST[:max_tickers]

    progress = st.progress(0)

    for i, symbol in enumerate(tickers):

        try:
            quote = get_quote(symbol)
            price = float(quote.get("last") or quote.get("close"))

            expirations = get_expirations(symbol)

            for exp in expirations[:4]:

                dte = (datetime.strptime(exp, "%Y-%m-%d").date() - datetime.now().date()).days

                if dte < 28 or dte > 45:
                    continue

                chain = get_chain(symbol, exp)

                puts = chain[chain["option_type"] == "put"]

                for _, row in puts.iterrows():

                    strike = float(row.get("strike", 0))
                    bid = float(row.get("bid", 0) or 0)
                    ask = float(row.get("ask", 0) or 0)

                    if bid <= 0 and ask <= 0:
                        continue

                    mid = (bid + ask) / 2 if ask > 0 else bid

                    greeks = row.get("greeks", {})

                    iv = greeks.get("mid_iv", 0)
                    delta = abs(float(greeks.get("delta", 0) or 0))

                    if iv > 5:
                        iv = iv / 100

                    expected_move = price * iv * np.sqrt(dte / 365)

                    if expected_move <= 0:
                        continue

                    sd_distance = (price - strike) / expected_move

                    roi = monthly_roi(mid, strike, dte)

                    score = 0

                    if roi >= 5:
                        score += 25

                    if sd_distance >= 2:
                        score += 25

                    if 0.10 <= delta <= 0.30:
                        score += 20

                    oi = float(row.get("open_interest", 0) or 0)

                    if oi >= 100:
                        score += 15

                    spread = ((ask - bid) / mid * 100) if mid > 0 else 999

                    if spread <= 25:
                        score += 15

                    action = "AVOID"

                    if score >= 75:
                        action = "BEST"
                    elif score >= 55:
                        action = "WATCH"

                    results.append({
                        "Ticker": symbol,
                        "Action": action,
                        "Score": round(score, 1),
                        "Price": round(price, 2),
                        "Expiration": exp,
                        "DTE": dte,
                        "Strike": strike,
                        "Delta": round(delta, 2),
                        "IV%": round(iv * 100, 1),
                        "Premium": round(mid * 100, 2),
                        "Monthly ROI %": round(roi, 2),
                        "SD Distance": round(sd_distance, 2),
                        "Open Interest": int(oi),
                        "Spread %": round(spread, 1),
                    })

        except Exception:
            pass

        progress.progress((i + 1) / len(tickers))

    df = pd.DataFrame(results)

    if len(df) == 0:
        st.error("No results.")
    else:
        df = df.sort_values(by=["Score", "Monthly ROI %"], ascending=False)

        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download CSV",
            csv,
            "csp_scan.csv",
            "text/csv"
        )
