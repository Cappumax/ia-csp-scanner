import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="IA CSP Scanner V3", layout="wide")

TOKEN = st.secrets.get("TRADIER_TOKEN", "")

WATCHLIST = [
    "NVDA", "ALAB", "AVGO", "MRVL", "AMD", "MU", "ASML", "TSM", "ANET",
    "GOOGL", "META", "MSFT", "AMZN", "PLTR", "CRM",
    "MSTR", "IBIT", "COIN", "GLXY", "CRCL",
    "RKLB", "ASTS", "ARM", "EOSE", "CPER", "SLV",
    "HOOD", "SOFI", "NBIS", "INFQ", "NVTS", "IREN", "TSLA"
]

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def tradier_get(endpoint, params=None):
    if not TOKEN:
        raise Exception("Missing TRADIER_TOKEN in Streamlit Secrets.")
    url = f"https://api.tradier.com/v1{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params or {}, timeout=25)
    if response.status_code != 200:
        raise Exception(f"Tradier API error {response.status_code}: {response.text[:250]}")
    return response.json()


@st.cache_data(ttl=180)
def get_quote(symbol):
    data = tradier_get("/markets/quotes", {"symbols": symbol})
    quote = data.get("quotes", {}).get("quote")
    if isinstance(quote, list):
        quote = quote[0] if quote else {}
    price = safe_float(quote.get("last") or quote.get("close"))
    if price <= 0:
        raise Exception(f"No valid quote for {symbol}")
    return price


@st.cache_data(ttl=600)
def get_expirations(symbol):
    data = tradier_get(
        "/markets/options/expirations",
        {"symbol": symbol, "includeAllRoots": "true", "strikes": "false"}
    )
    dates = as_list(data.get("expirations", {}).get("date"))
    if not dates:
        raise Exception(f"No option expirations for {symbol}")
    return dates


@st.cache_data(ttl=300)
def get_chain(symbol, expiration):
    data = tradier_get(
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"}
    )
    options = as_list(data.get("options", {}).get("option"))
    if not options:
        return pd.DataFrame()
    return pd.DataFrame(options)


@st.cache_data(ttl=900)
def get_history(symbol):
    data = tradier_get(
        "/markets/history",
        {
            "symbol": symbol,
            "interval": "daily",
            "start": "2025-01-01",
            "end": datetime.now().strftime("%Y-%m-%d")
        }
    )
    days = as_list(data.get("history", {}).get("day"))
    closes = []
    for day in days:
        close = safe_float(day.get("close"))
        if close > 0:
            closes.append(close)
    return closes


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))), 2)


def calculate_trend(closes):
    if len(closes) < 200:
        return "UNKNOWN", 0.0, 0.0
    sma50 = float(np.mean(closes[-50:]))
    sma200 = float(np.mean(closes[-200:]))
    trend = "BULLISH" if sma50 > sma200 else "BEARISH"
    return trend, round(sma50, 2), round(sma200, 2)


def estimate_iv_rank(iv):
    if iv <= 0:
        return 0.0
    iv_percent = iv * 100
    if iv_percent >= 100:
        return 90.0
    if iv_percent >= 80:
        return 80.0
    if iv_percent >= 60:
        return 65.0
    if iv_percent >= 40:
        return 45.0
    if iv_percent >= 25:
        return 30.0
    return 15.0


def assignment_risk(delta, sd_distance, trend):
    risk_points = 0
    if delta >= 0.30:
        risk_points += 40
    elif delta >= 0.25:
        risk_points += 30
    elif delta >= 0.15:
        risk_points += 20
    else:
        risk_points += 10

    if sd_distance < 1:
        risk_points += 35
    elif sd_distance < 1.5:
        risk_points += 25
    elif sd_distance < 2:
        risk_points += 15
    else:
        risk_points += 5

    if trend == "BEARISH":
        risk_points += 20

    if risk_points >= 70:
        return "HIGH"
    if risk_points >= 40:
        return "MEDIUM"
    return "LOW"


def make_commentary(action, monthly_roi, delta, prob_otm, trend, rsi, spread, assignment):
    notes = []
    if action == "BEST":
        notes.append("Strong scanner setup.")
    elif action == "WATCH":
        notes.append("Possible setup; verify chart and broker quote.")
    else:
        notes.append("Avoid unless you have a strong reason.")

    if monthly_roi >= 5:
        notes.append("Premium is rich.")
    elif monthly_roi < 2:
        notes.append("Premium may not justify the capital.")

    if 0.15 <= delta <= 0.25:
        notes.append("Delta is in the preferred CSP zone.")
    elif delta > 0.30:
        notes.append("Delta is aggressive.")

    if prob_otm >= 75:
        notes.append("Probability OTM is favorable.")

    if trend == "BULLISH":
        notes.append("Trend is supportive.")
    elif trend == "BEARISH":
        notes.append("Bearish trend increases assignment risk.")

    if rsi >= 70:
        notes.append("RSI is extended; avoid chasing.")
    elif rsi <= 35:
        notes.append("RSI is oversold; possible bounce zone.")

    if spread > 25:
        notes.append("Bid/ask spread is wide.")

    if assignment == "HIGH":
        notes.append("Assignment risk is high.")

    return " ".join(notes)


st.title("💰 IA CSP Scanner V3")
st.caption(
    "Cash-secured put scanner using Tradier data. Research only. "
    "Always verify quote, liquidity, earnings, and chart in your broker before trading."
)

if not TOKEN:
    st.error("Missing TRADIER_TOKEN. Add it in Streamlit → Manage App → Settings → Secrets.")
    st.stop()

with st.sidebar:
    st.header("Scanner Settings")
    max_tickers = st.slider("Tickers to scan", 1, len(WATCHLIST), 10)
    min_dte = st.slider("Minimum DTE", 7, 90, 28)
    max_dte = st.slider("Maximum DTE", min_dte, 120, 45)
    target_monthly_roi = st.slider("Target Monthly ROI %", 0.5, 10.0, 3.0, 0.25)
    target_sd_distance = st.slider("Target SD Distance", 0.5, 5.0, 2.0, 0.25)

    st.header("Filters")
    use_delta_filter = st.checkbox("Use Delta Filter", value=True)
    min_delta = st.slider("Minimum Delta", 0.01, 0.50, 0.15, 0.01)
    max_delta = st.slider("Maximum Delta", min_delta, 0.60, 0.25, 0.01)
    best_watch_only = st.checkbox("Only show BEST/WATCH", value=True)
    premium_over_300 = st.checkbox("Only premium over $300", value=False)
    bullish_only = st.checkbox("Bullish trend only", value=False)
    best_per_ticker = st.checkbox("Only best contract per ticker", value=True)

selected_tickers = WATCHLIST[:max_tickers]
st.write("**Selected tickers:**", ", ".join(selected_tickers))

if st.button("Run CSP Scan", type="primary"):
    results = []
    errors = []
    progress = st.progress(0)

    for i, symbol in enumerate(selected_tickers):
        try:
            price = get_quote(symbol)
            closes = get_history(symbol)
            rsi = calculate_rsi(closes)
            trend, sma50, sma200 = calculate_trend(closes)
            expirations = get_expirations(symbol)

            for exp in expirations:
                dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                if dte < min_dte or dte > max_dte:
                    continue

                chain_df = get_chain(symbol, exp)
                if chain_df.empty or "option_type" not in chain_df.columns:
                    continue

                puts = chain_df[chain_df["option_type"].astype(str).str.lower() == "put"]

                for _, option in puts.iterrows():
                    strike = safe_float(option.get("strike"))
                    if strike <= 0 or strike >= price:
                        continue

                    bid = safe_float(option.get("bid"))
                    ask = safe_float(option.get("ask"))
                    last = safe_float(option.get("last"))

                    if bid > 0 and ask > 0 and ask >= bid:
                        mid = (bid + ask) / 2
                    elif last > 0:
                        mid = last
                    else:
                        continue

                    if mid <= 0:
                        continue

                    greeks = option.get("greeks", {})
                    if not isinstance(greeks, dict):
                        greeks = {}

                    delta = abs(safe_float(greeks.get("delta")))
                    iv = safe_float(greeks.get("mid_iv"))
                    if iv <= 0:
                        iv = safe_float(greeks.get("smv_vol"))
                    if iv > 5:
                        iv = iv / 100
                    if iv <= 0:
                        continue

                    expected_move = price * iv * np.sqrt(dte / 365)
                    if expected_move <= 0:
                        continue

                    sd_distance = (price - strike) / expected_move
                    premium = mid * 100
                    capital_required = strike * 100
                    monthly_roi = (premium / capital_required) * (30 / dte) * 100
                    annualized_yield = monthly_roi * 12
                    premium_per_week = premium / (dte / 7)
                    prob_otm = max(0, min(100, (1 - delta) * 100))
                    iv_rank_estimate = estimate_iv_rank(iv)
                    volume = safe_float(option.get("volume"))
                    open_interest = safe_float(option.get("open_interest"))
                    spread_percent = ((ask - bid) / mid) * 100 if ask > 0 and bid > 0 else 999
                    assignment = assignment_risk(delta, sd_distance, trend)

                    score = 0
                    if monthly_roi >= target_monthly_roi:
                        score += 20
                    elif monthly_roi >= target_monthly_roi * 0.70:
                        score += 10

                    if sd_distance >= target_sd_distance:
                        score += 20
                    elif sd_distance >= 1.5:
                        score += 10

                    if min_delta <= delta <= max_delta:
                        score += 15
                    elif 0.10 <= delta <= 0.30:
                        score += 10

                    if prob_otm >= 75:
                        score += 10

                    if trend == "BULLISH":
                        score += 10
                    elif trend == "BEARISH":
                        score -= 10

                    if rsi < 70:
                        score += 5

                    if open_interest >= 100:
                        score += 10

                    if spread_percent <= 25:
                        score += 10

                    score = max(0, min(100, score))

                    if score >= 75:
                        action = "BEST"
                    elif score >= 55:
                        action = "WATCH"
                    else:
                        action = "AVOID"

                    commentary = make_commentary(
                        action,
                        monthly_roi,
                        delta,
                        prob_otm,
                        trend,
                        rsi,
                        spread_percent,
                        assignment
                    )

                    results.append({
                        "Ticker": symbol,
                        "Action": action,
                        "Score": round(score, 1),
                        "Price": round(price, 2),
                        "Strike": round(strike, 2),
                        "Expiration": exp,
                        "DTE": dte,
                        "Bid": round(bid, 2),
                        "Ask": round(ask, 2),
                        "Premium": round(premium, 2),
                        "Premium/Week": round(premium_per_week, 2),
                        "Capital Required": round(capital_required, 2),
                        "Monthly ROI %": round(monthly_roi, 2),
                        "Annualized Yield %": round(annualized_yield, 2),
                        "Delta": round(delta, 3),
                        "Probability OTM %": round(prob_otm, 1),
                        "IV %": round(iv * 100, 2),
                        "IV Rank Estimate": round(iv_rank_estimate, 1),
                        "RSI": round(rsi, 1),
                        "SMA50": round(sma50, 2),
                        "SMA200": round(sma200, 2),
                        "Trend": trend,
                        "Volume": int(volume),
                        "Open Interest": int(open_interest),
                        "Spread %": round(spread_percent, 2),
                        "Assignment Risk": assignment,
                        "Earnings Check": "VERIFY BEFORE TRADE",
                        "AI Commentary": commentary
                    })

        except Exception as e:
            errors.append({"Ticker": symbol, "Error": str(e)})

        progress.progress((i + 1) / len(selected_tickers))

    if results:
        df = pd.DataFrame(results)

        if use_delta_filter:
            df = df[(df["Delta"] >= min_delta) & (df["Delta"] <= max_delta)]

        if best_watch_only:
            df = df[df["Action"].isin(["BEST", "WATCH"])]

        if premium_over_300:
            df = df[df["Premium"] >= 300]

        if bullish_only:
            df = df[df["Trend"] == "BULLISH"]

        if not df.empty:
            df = df.sort_values(
                by=["Annualized Yield %", "Score", "Probability OTM %"],
                ascending=[False, False, False]
            )

            if best_per_ticker:
                df = df.groupby("Ticker").head(1).reset_index(drop=True)

            st.subheader("CSP Scan Results")

            st.dataframe(df, use_container_width=True, height=700)

            csv = df.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download CSV",
                csv,
                "ia_csp_scan.csv",
                "text/csv"
            )
        else:
            st.warning("No setups matched your filters. Try lowering ROI, turning off delta filter, or widening DTE.")
    else:
        st.error("No CSP setups found.")

    if errors:
        st.subheader("Errors / Debug")
        st.dataframe(pd.DataFrame(errors), use_container_width=True)
