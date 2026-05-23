
# IA Philosophy Aligned CSP Scanner

This Streamlit app scans your IA-aligned watchlist for cash-secured put candidates.

## What it scans

- 28–45 DTE options
- Put strikes near/beyond -2 standard deviation
- Monthly ROI target, default 5%
- Bid/ask spread
- Open interest and volume
- Basic chart context:
  - RSI 14
  - 20/50/200 SMA
  - 3-month support

## Important warning

This app uses free Yahoo Finance data through `yfinance`.

That means:
- data can be delayed
- chains can be stale
- some tickers may be missing
- Greeks may not be available
- final trade must be verified in your broker

Do not place trades directly from this app without checking Thinkorswim, Schwab, Fidelity, Robinhood, or another broker.

## How to run

1. Install Python 3.10 or newer.
2. Open Terminal or Command Prompt.
3. Navigate into this folder.
4. Run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Starting recommendation

Start scanning only 5–10 tickers at a time because Yahoo can throttle requests.

Suggested first scan:
- TSLA
- NVDA
- PLTR
- COIN
- MSTR
- META
- MSFT
- SOFI
- HOOD
- IREN

## How to interpret

BEST = Strong candidate based on scanner rules  
WATCH = Possible, but needs chart/quote review  
AVOID = Weak risk/reward or poor data/liquidity  

## My preferred trading rule

Do not chase 5% monthly premium blindly. High premium usually means high risk.

Best setup:
- high-quality name
- clean support
- no earnings before expiration
- decent liquidity
- strike near/below -2 SD
- premium is attractive but not suspicious
