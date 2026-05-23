
"""
IA Philosophy Aligned CSP Scanner
Author: ChatGPT for Isha

Purpose:
Scan a custom IA-style watchlist for cash-secured put opportunities using free Yahoo Finance
data through yfinance.

IMPORTANT:
- This is an educational/research tool, not financial advice.
- Yahoo/yfinance options data can be delayed, stale, incomplete, or temporarily unavailable.
- Always verify the final option quote, bid/ask, earnings date, and chart in your broker before trading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


WATCHLIST_GROUPS: Dict[str, List[str]] = {
    "AI Hardware & Infrastructure": ["NVDA", "ALAB", "AVGO", "MRVL", "AMD", "MU", "ASML", "TSM", "ANET"],
    "AI Software & Platforms": ["GOOGL", "META", "MSFT", "AMZN", "PLTR", "CRM"],
    "Bitcoin & Crypto": ["MSTR", "IBIT", "COIN", "GLXY", "CRCL"],
    "Space & Defense": ["RKLB", "ASTS", "ARM"],
    "Energy & Infrastructure": ["EOSE", "CPER", "SLV"],
    "Fintech": ["HOOD", "SOFI"],
    "Asymmetric/Emerging": ["NBIS", "INFQ", "NVTS", "IREN"],
    "Autonomous & Robotics": ["TSLA"],
}


@dataclass
class ScanSettings:
    min_dte: int = 28
    max_dte: int = 45
    target_monthly_roi: float = 5.0
    min_open_interest: int = 100
    max_bid_ask_spread_pct: float = 20.0
    sd_target: float = 2.0


def today_date() -> date:
    return datetime.now().date()


def safe_float(value, default=np.nan) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


@st.cache_data(ttl=900, show_spinner=False)
def get_price_history(ticker: str) -> pd.DataFrame:
    try:
        hist = yf.Ticker(ticker).history(period="1y", auto_adjust=False)
        if hist is None or hist.empty:
            return pd.DataFrame()
        return hist.reset_index()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def get_options_dates(ticker: str) -> Tuple[str, ...]:
    try:
        return tuple(yf.Ticker(ticker).options)
    except Exception:
        return tuple()


@st.cache_data(ttl=900, show_spinner=False)
def get_put_chain(ticker: str, expiry: str) -> pd.DataFrame:
    try:
        chain = yf.Ticker(ticker).option_chain(expiry)
        puts = chain.puts.copy()
        if puts.empty:
            return pd.DataFrame()
        puts["expiry"] = expiry
        return puts
    except Exception:
        return pd.DataFrame()


def compute_technicals(hist: pd.DataFrame) -> dict:
    if hist.empty or "Close" not in hist:
        return {
            "last_price": np.nan,
            "rsi14": np.nan,
            "sma20": np.nan,
            "sma50": np.nan,
            "sma200": np.nan,
            "support_3m": np.nan,
        }

    close = hist["Close"].astype(float)
    last_price = close.iloc[-1]

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi14 = 100 - (100 / (1 + rs))

    return {
        "last_price": float(last_price),
        "rsi14": safe_float(rsi14.iloc[-1]),
        "sma20": safe_float(close.rolling(20).mean().iloc[-1]),
        "sma50": safe_float(close.rolling(50).mean().iloc[-1]),
        "sma200": safe_float(close.rolling(200).mean().iloc[-1]),
        "support_3m": safe_float(close.tail(63).min()),
    }


def dte_from_expiry(expiry: str) -> int:
    return (datetime.strptime(expiry, "%Y-%m-%d").date() - today_date()).days


def annualized_to_period_expected_move(price: float, iv: float, dte: int) -> float:
    if price <= 0 or iv <= 0 or dte <= 0:
        return np.nan
    return price * iv * math.sqrt(dte / 365)


def monthly_roi_pct(mid: float, strike: float, dte: int) -> float:
    if strike <= 0 or dte <= 0:
        return np.nan
    return (mid / strike) * (30 / dte) * 100


def spread_pct(bid: float, ask: float, mid: float) -> float:
    if mid <= 0:
        return np.nan
    return ((ask - bid) / mid) * 100


def score_candidate(row: pd.Series, settings: ScanSettings):
    score = 0
    reasons = []

    roi = safe_float(row.get("monthly_roi_pct"))
    if roi >= settings.target_monthly_roi:
        score += 25
        reasons.append("meets ROI target")
    elif roi >= settings.target_monthly_roi * 0.70:
        score += 15
        reasons.append("near ROI target")
    else:
        reasons.append("premium below target")

    sd_dist = safe_float(row.get("sd_distance"))
    if sd_dist >= settings.sd_target:
        score += 20
        reasons.append("near/beyond -2 SD")
    elif sd_dist >= 1.5:
        score += 12
        reasons.append("moderately OTM by SD")
    else:
        reasons.append("not far enough OTM")

    oi = safe_float(row.get("openInterest"), 0)
    vol = safe_float(row.get("volume"), 0)
    if oi >= settings.min_open_interest and vol >= 25:
        score += 15
        reasons.append("acceptable liquidity")
    elif oi >= settings.min_open_interest:
        score += 10
        reasons.append("OI okay, volume light")
    else:
        reasons.append("weak open interest")

    spread = safe_float(row.get("bid_ask_spread_pct"))
    if not np.isnan(spread) and spread <= settings.max_bid_ask_spread_pct:
        score += 15
        reasons.append("spread acceptable")
    else:
        reasons.append("wide bid/ask")

    price = safe_float(row.get("price"))
    strike = safe_float(row.get("strike"))
    support = safe_float(row.get("support_3m"))
    sma50 = safe_float(row.get("sma50"))
    sma200 = safe_float(row.get("sma200"))
    rsi = safe_float(row.get("rsi14"))

    if not np.isnan(support) and strike <= support * 1.03:
        score += 10
        reasons.append("strike near/below 3M support")
    else:
        reasons.append("strike above recent support")

    if not np.isnan(sma50) and not np.isnan(sma200) and price >= sma50 >= sma200:
        score += 10
        reasons.append("trend healthy")
    elif not np.isnan(rsi) and rsi < 35:
        score += 5
        reasons.append("oversold/reversion candidate")
    else:
        reasons.append("trend not ideal")

    if score >= 75:
        action = "BEST"
    elif score >= 55:
        action = "WATCH"
    else:
        action = "AVOID"

    return score, action, "; ".join(reasons)


def scan_ticker(ticker: str, settings: ScanSettings) -> pd.DataFrame:
    hist = get_price_history(ticker)
    tech = compute_technicals(hist)
    price = tech["last_price"]

    if np.isnan(price) or price <= 0:
        return pd.DataFrame([{"ticker": ticker, "error": "No price data"}])

    expiries = get_options_dates(ticker)
    if not expiries:
        return pd.DataFrame([{
            "ticker": ticker,
            "price": price,
            "error": "No options expirations from Yahoo/yfinance"
        }])

    valid_expiries = [e for e in expiries if settings.min_dte <= dte_from_expiry(e) <= settings.max_dte]
    if not valid_expiries:
        return pd.DataFrame([{
            "ticker": ticker,
            "price": price,
            "error": f"No expirations between {settings.min_dte}-{settings.max_dte} DTE"
        }])

    rows = []
    for expiry in valid_expiries:
        dte = dte_from_expiry(expiry)
        puts = get_put_chain(ticker, expiry)
        if puts.empty:
            continue

        for _, opt in puts.iterrows():
            strike = safe_float(opt.get("strike"))
            bid = safe_float(opt.get("bid"), 0)
            ask = safe_float(opt.get("ask"), 0)
            last_price_opt = safe_float(opt.get("lastPrice"), 0)
            iv = safe_float(opt.get("impliedVolatility"))
            oi = safe_float(opt.get("openInterest"), 0)
            vol = safe_float(opt.get("volume"), 0)

            if strike <= 0 or iv <= 0:
                continue

            if bid > 0 and ask > 0 and ask >= bid:
                mid = (bid + ask) / 2
            else:
                mid = last_price_opt

            if mid <= 0:
                continue

            expected_move_1sd = annualized_to_period_expected_move(price, iv, dte)
            if np.isnan(expected_move_1sd) or expected_move_1sd <= 0:
                continue

            sd_distance = (price - strike) / expected_move_1sd
            target_2sd_strike = price - settings.sd_target * expected_move_1sd

            category = next((cat for cat, lst in WATCHLIST_GROUPS.items() if ticker in lst), "Custom")

            candidate = {
                "ticker": ticker,
                "category": category,
                "expiry": expiry,
                "dte": dte,
                "price": price,
                "strike": strike,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "premium_income": mid * 100,
                "cash_required": strike * 100,
                "monthly_roi_pct": monthly_roi_pct(mid, strike, dte),
                "impliedVolatility": iv,
                "iv_pct": iv * 100,
                "openInterest": oi,
                "volume": vol,
                "bid_ask_spread_pct": spread_pct(bid, ask, mid),
                "target_2sd_strike": target_2sd_strike,
                "sd_distance": sd_distance,
                "rsi14": tech["rsi14"],
                "sma20": tech["sma20"],
                "sma50": tech["sma50"],
                "sma200": tech["sma200"],
                "support_3m": tech["support_3m"],
                "error": "",
            }

            score, action, reasons = score_candidate(pd.Series(candidate), settings)
            candidate["score"] = score
            candidate["action"] = action
            candidate["reasons"] = reasons
            rows.append(candidate)

    if not rows:
        return pd.DataFrame([{
            "ticker": ticker,
            "price": price,
            "error": "No usable put contracts after filters/data checks"
        }])

    df = pd.DataFrame(rows)
    df["distance_from_2sd_abs"] = (df["sd_distance"] - settings.sd_target).abs()
    return df


def display_metric_block(df: pd.DataFrame):
    best_count = int((df.get("action") == "BEST").sum()) if "action" in df else 0
    watch_count = int((df.get("action") == "WATCH").sum()) if "action" in df else 0
    avoid_count = int((df.get("action") == "AVOID").sum()) if "action" in df else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contracts scanned", f"{len(df):,}")
    c2.metric("BEST", best_count)
    c3.metric("WATCH", watch_count)
    c4.metric("AVOID", avoid_count)


def main():
    st.set_page_config(page_title="IA CSP Scanner", page_icon="💰", layout="wide")

    st.title("💰 IA Philosophy Aligned CSP Scanner")
    st.caption(
        "Scans 28–45 DTE cash-secured puts using free Yahoo/yfinance data. "
        "Research tool only. Verify every final quote in your broker."
    )

    with st.sidebar:
        st.header("Scanner Settings")

        preset = st.radio("Watchlist", ["Use IA Final CSP List", "Custom tickers"], index=0)

        if preset == "Use IA Final CSP List":
            selected_groups = st.multiselect(
                "Groups",
                list(WATCHLIST_GROUPS.keys()),
                default=list(WATCHLIST_GROUPS.keys()),
            )
            tickers = sorted({t for g in selected_groups for t in WATCHLIST_GROUPS[g]})
        else:
            raw = st.text_area(
                "Enter tickers separated by commas",
                value="TSLA,NVDA,PLTR,COIN,IBIT",
                height=120,
            )
            tickers = sorted({x.strip().upper() for x in raw.split(",") if x.strip()})

        min_dte = st.slider("Minimum DTE", 7, 90, 28)
        max_dte = st.slider("Maximum DTE", min_dte, 120, 45)
        target_monthly_roi = st.slider("Target monthly ROI %", 0.5, 10.0, 5.0, 0.25)
        sd_target = st.slider("SD target", 1.0, 3.0, 2.0, 0.25)
        min_open_interest = st.number_input("Minimum open interest", min_value=0, value=100, step=50)
        max_spread = st.slider("Max bid/ask spread %", 5.0, 100.0, 20.0, 1.0)

        max_tickers = st.slider(
            "Max tickers to scan now",
            min_value=1,
            max_value=max(1, len(tickers)),
            value=min(10, max(1, len(tickers))),
            help="Yahoo can throttle requests. Start with 5–10."
        )

        st.warning("Yahoo/yfinance is free but unofficial. Data may be delayed, stale, missing, or wrong.")

    settings = ScanSettings(
        min_dte=min_dte,
        max_dte=max_dte,
        target_monthly_roi=target_monthly_roi,
        min_open_interest=int(min_open_interest),
        max_bid_ask_spread_pct=max_spread,
        sd_target=sd_target,
    )

    tickers_to_scan = tickers[:max_tickers]

    st.subheader("Selected Watchlist")
    st.write(", ".join(tickers_to_scan))

    if st.button("Run CSP Scan", type="primary"):
        all_results = []
        progress = st.progress(0)
        status = st.empty()

        for i, ticker in enumerate(tickers_to_scan, start=1):
            status.write(f"Scanning {ticker} ({i}/{len(tickers_to_scan)})...")
            result = scan_ticker(ticker, settings)
            all_results.append(result)
            progress.progress(i / len(tickers_to_scan))

        df = pd.concat(all_results, ignore_index=True)

        errors = df[df.get("error", "") != ""] if "error" in df.columns else pd.DataFrame()
        usable = df[df.get("error", "") == ""].copy() if "error" in df.columns else df.copy()

        if usable.empty:
            st.error("No usable CSP candidates. Check data availability or loosen filters.")
            if not errors.empty:
                st.dataframe(errors, use_container_width=True)
            return

        usable = usable.sort_values(
            by=["score", "monthly_roi_pct", "sd_distance"],
            ascending=[False, False, False],
        )

        display_metric_block(usable)

        show_cols = [
            "action", "score", "ticker", "category", "price", "expiry", "dte", "strike",
            "bid", "ask", "mid", "premium_income", "cash_required", "monthly_roi_pct",
            "sd_distance", "target_2sd_strike", "iv_pct", "openInterest", "volume",
            "bid_ask_spread_pct", "rsi14", "sma50", "sma200", "support_3m", "reasons"
        ]
        show_cols = [c for c in show_cols if c in usable.columns]

        st.subheader("Top CSP Candidates")
        st.dataframe(usable[show_cols].round(2), use_container_width=True, height=600)

        st.subheader("Best Per Ticker")
        best_per_ticker = (
            usable.sort_values(["ticker", "score", "monthly_roi_pct"], ascending=[True, False, False])
            .groupby("ticker", as_index=False)
            .head(1)
        )
        st.dataframe(best_per_ticker[show_cols].round(2), use_container_width=True)

        csv = usable.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download full scan CSV",
            csv,
            file_name=f"ia_csp_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

        if not errors.empty:
            st.subheader("Data Issues")
            st.dataframe(errors, use_container_width=True)

        st.info(
            "Final trade checklist: verify quote in broker, confirm no earnings/FOMC/event risk, "
            "check chart support, and only sell puts on names you are willing to own."
        )


if __name__ == "__main__":
    main()
