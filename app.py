import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="IA CSP Scanner - Tradier", layout="wide")

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
        raise Exception("Missing TRADIER_TOKEN in Streamlit Secrets.")

    url = f"https://api.tradier.com/v1{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params or {}, timeout=20)

    if response.status_code != 200:
        raise Exception(f"Tradier API Error {response.status_code}: {response.text[:250]}")

    return response.json()

def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default

def get_quote(symbol):
    data = tradier_get("/markets/quotes", {"symbols": symbol})
    quote = data.get("quotes", {}).get("quote")

    if isinstance(quote, list):
        quote = quote[0] if quote else {}

    price = safe_float(quote.get("last") or quote.get("close"))
    if price <= 0:
        raise Exception(f"No valid price for {symbol}")

    return price

def get_expirations(symbol):
    data = tradier_get(
        "/markets/options/expirations",
        {"symbol": symbol, "includeAllRoots": "true"}
    )
    dates = as_list(data.get("expirations", {}).get("date"))

    if not dates:
        raise Exception(f"No expirations for {symbol}")

    return dates

def get_chain(symbol, expiration):
    data = tradier_get(
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"}
    )

    options = as_list(data.get("options", {}).get("option"))

    if not options:
        return pd.DataFrame()

    return pd.DataFrame(options)

def get_history(symbol):
    end = datetime.now().date()
    start = end - timedelta(days=365)

    data = tradier_get(
        "/markets/history",
        {
            "symbol": symbol,
            "interval": "daily",
            "start": start.isoformat(),
            "end": end.isoformat()
        }
    )

    days = as_list(data.get("history", {}).get("day"))

    if not days:
        return pd.DataFrame()

    df = pd.DataFrame(days)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df

def add_technicals(df):
    if df.empty:
        return df

    df["SMA50"] = df["close"].rolling(50).mean()
    df["SMA200"] = df["close"].rolling(200).mean()
    df["BB_Mid"] = df["close"].rolling(20).mean()
    df["BB_Upper"] = df["BB_Mid"] + 2 * df["close"].rolling(20).std()
    df["BB_Lower"] = df["BB_Mid"] - 2 * df["close"].rolling(20).std()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    return df

def monthly_roi(mid, strike, dte):
    if strike <= 0 or dte <= 0:
        return 0
    return (mid / strike) * (30 / dte) * 100

def greek_value(greeks, key):
    if isinstance(greeks, dict):
        return safe_float(greeks.get(key), 0)
    return 0

def ai_commentary(action, roi, sd_distance, delta, spread, oi, dte):
    notes = []

    if action == "BEST":
        notes.append("Strong CSP candidate based on scanner rules.")
    elif action == "WATCH":
        notes.append("Possible setup, but needs chart and broker review.")
    else:
        notes.append("Avoid unless you have a strong reason.")

    if roi >= 5:
        notes.append("Premium is rich.")
    elif roi < 2:
        notes.append("Premium may not be worth the capital.")

    if sd_distance >= 2:
        notes.append("Strike has good downside cushion.")
    else:
        notes.append("Strike is not far enough below price.")

    if delta > 0.30:
        notes.append("Delta is aggressive for CSP.")
    elif 0.15 <= delta <= 0.25:
        notes.append("Delta is in a sweet spot.")

    if spread > 25:
        notes.append("Bid/ask spread is wide.")
    if oi < 100:
        notes.append("Open interest is low.")

    return " ".join(notes)

st.title("💰 IA CSP Scanner - Tradier")
st.caption("Cash-secured put scanner for your IA-style watchlist. Research only. Verify every trade in your broker.")

if not TOKEN:
    st.error("Missing TRADIER_TOKEN. Add it in Streamlit → Manage App → Settings → Secrets.")
    st.stop()

with st.sidebar:
    st.header("Scanner Settings")

    max_tickers = st.slider("Tickers to scan", 1, len(WATCHLIST), 5)
    min_dte = st.slider("Minimum DTE", 1, 90, 28)
    max_dte = st.slider("Maximum DTE", min_dte, 120, 45)
    target_roi = st.slider("Target monthly ROI %", 0.5, 10.0, 5.0, 0.25)
    target_sd = st.slider("Target SD distance", 1.0, 3.0, 2.0, 0.25)
st.subheader("Filters")

best_only = st.checkbox(
    "Only show BEST/WATCH",
    value=True
)

min_delta = st.slider(
    "Minimum Delta",
    0.01,
    0.50,
    0.15,
    0.01
)

max_delta = st.slider(
    "Maximum Delta",
    min_delta,
    0.50,
    0.25,
    0.01
)

delta_filter = st.checkbox(
    "Use delta filter",
    value=False
)

premium_filter = st.checkbox(
    "Only premium over $300",
    value=False
)

best_per_ticker = st.checkbox(
    "Only best contract per ticker",
    value=True
)
    

selected_tickers = WATCHLIST[:max_tickers]
st.write("**Selected tickers:**", ", ".join(selected_tickers))

if st.button("Run CSP Scan", type="primary"):

    results = []
    errors = []
    progress = st.progress(0)

    for i, symbol in enumerate(selected_tickers):

        try:
            price = get_quote(symbol)
            expirations = get_expirations(symbol)

            for exp in expirations:

                dte = (datetime.strptime(exp, "%Y-%m-%d").date() - datetime.now().date()).days

                if dte < min_dte or dte > max_dte:
                    continue

                chain = get_chain(symbol, exp)

                if chain.empty or "option_type" not in chain.columns:
                    continue

                puts = chain[chain["option_type"].astype(str).str.lower() == "put"]

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
                    delta = abs(greek_value(greeks, "delta"))

                    iv = greek_value(greeks, "mid_iv")
                    if iv <= 0:
                        iv = greek_value(greeks, "smv_vol")
                    if iv > 5:
                        iv = iv / 100
                    if iv <= 0:
                        continue

                    expected_move = price * iv * np.sqrt(dte / 365)

                    if expected_move <= 0:
                        continue

                    sd_distance = (price - strike) / expected_move
                    roi = monthly_roi(mid, strike, dte)
                    annualized_yield = (mid / strike) * (365 / dte) * 100
                    premium = mid * 100
                    premium_per_week = premium / (dte / 7)
                    capital_required = strike * 100
                    oi = safe_float(row.get("open_interest"))
                    volume = safe_float(row.get("volume"))
                    spread = ((ask - bid) / mid * 100) if bid > 0 and ask > 0 and mid > 0 else 999

                    score = 0

                    if roi >= target_roi:
                        score += 25
                    elif roi >= target_roi * 0.70:
                        score += 15

                    if sd_distance >= target_sd:
                        score += 25
                    elif sd_distance >= 1.5:
                        score += 15

                    if 0.15 <= delta <= 0.25:
                        score += 20
                    elif 0.10 <= delta <= 0.30:
                        score += 15

                    if oi >= 100:
                        score += 15

                    if spread <= 25:
                        score += 15

                    if score >= 75:
                        action = "BEST"
                    elif score >= 55:
                        action = "WATCH"
                    else:
                        action = "AVOID"

                    comment = ai_commentary(action, roi, sd_distance, delta, spread, oi, dte)

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
                        "Premium": round(premium, 2),
                        "Premium Per Week": round(premium_per_week, 2),
                        "Monthly ROI %": round(roi, 2),
                        "Annualized Yield %": round(annualized_yield, 2),
                        "Capital Required": round(capital_required, 2),
                        "SD Distance": round(sd_distance, 2),
                        "Delta": round(delta, 3),
                        "IV %": round(iv * 100, 2),
                        "Open Interest": int(oi),
                        "Volume": int(volume),
                        "Spread %": round(spread, 2),
                        "AI Commentary": comment
                    })

        except Exception as e:
            errors.append({
                "Ticker": symbol,
                "Error": str(e)
            })

        progress.progress((i + 1) / len(selected_tickers))

    if results:

        df = pd.DataFrame(results)

        if best_only:
            df = df[df["Action"].isin(["BEST", "WATCH"])]

 if delta_filter:
    df = df[
        (df["Delta"] >= min_delta) &
        (df["Delta"] <= max_delta)
    ]        

        if premium_filter:
            df = df[df["Premium"] >= 300]

        if not df.empty:

            df = df.sort_values(
                by=["Ticker", "Score", "Monthly ROI %", "SD Distance"],
                ascending=[True, False, False, False]
            )

            if best_per_ticker:
                df = df.groupby("Ticker").head(1).reset_index(drop=True)

            st.subheader("CSP Scan Results")
            st.dataframe(df, use_container_width=True, height=600)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "csp_scan.csv", "text/csv")

        else:
            st.warning("No results after filters. Try turning off filters or widening DTE.")

    else:
        st.error("No CSP candidates found.")

    if errors:
        st.subheader("Debug / Errors")
        st.dataframe(pd.DataFrame(errors), use_container_width=True)

    st.subheader("Chart Preview")

    chart_ticker = st.selectbox("Choose ticker for chart", selected_tickers)

    try:
        hist = get_history(chart_ticker)
        hist = add_technicals(hist)

        if not hist.empty:
            chart_df = hist[["close", "SMA50", "SMA200", "BB_Upper", "BB_Lower"]].dropna()
            st.line_chart(chart_df)

            latest_rsi = round(hist["RSI"].dropna().iloc[-1], 2)
            st.write(f"**Latest RSI:** {latest_rsi}")

        else:
            st.warning("No chart history available.")

    except Exception as e:
        st.warning(f"Chart unavailable: {e}")
