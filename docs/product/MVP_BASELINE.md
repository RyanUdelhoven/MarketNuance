# Stock discovery MVP

A local browser app using Alpaca market data and SEC annual fundamentals. Every non-demo screen checks current Alpaca snapshots. SEC runs only for Alpaca survivors when financial criteria are active.

## Demo

```sh
python3 app.py --demo
```

Open http://127.0.0.1:8765. The invented rows are labeled **SYNTHETIC DEMO**. Set thresholds and click **Screen demo**; sort the results, save a local watchlist, or export CSV. Demo screens never contact providers.

## Fresh screen requests

In normal mode, clicking **Refresh & screen** sends `POST /api/screen`. The service refreshes current Alpaca snapshots, incrementally fills historical gaps, and applies market criteria. If no financial filter is active, it returns immediately without SEC. Otherwise, it checks SEC filing metadata only for survivors and downloads Company Facts only when missing or changed.

Assets cache for one day. Historical bars persist by feed. Only one screen refresh runs at once. Failures preserve the last complete snapshot.

## Refresh real data

Get free Alpaca **paper** API keys in your Alpaca dashboard. Set an SEC User-Agent with your actual name and email so the SEC can contact you about automated access. Run in the extracted `stock-discovery` directory in the same Terminal session:

```sh
export APCA_API_KEY_ID='YOUR_PAPER_KEY_ID'
export APCA_API_SECRET_KEY='YOUR_PAPER_SECRET'
export SEC_USER_AGENT='Your Name your-email@example.com'
python3 app.py --refresh --symbols AAPL,MSFT
python3 app.py
```

Open http://127.0.0.1:8765; Ctrl+C stops the server. Refreshes process the complete eligible Alpaca universe by default. Set `NOODLE_SCREEN_LIMIT` or pass `--limit` to cap development runs. Full initial history collection may take time. Refresh after market close for final daily bars.

Alpaca history is stored in `data/cache/alpaca/`; SEC facts remain in `data/cache/sec/`. SEC Submissions verifies whether a newer annual filing exists before refreshing facts. The interface visually separates market and financial filters and reports whether SEC ran.

## Metrics

The default screen uses a $15 minimum price, $30 maximum price, and 10,000 minimum
20-day average volume. Each filter includes an information icon describing its calculation.

| Field | Meaning |
|---|---|
| Close | Latest daily price in USD |
| Average volume | Mean share volume for 20 daily sessions |
| Return | Price change across 20 sessions; requires 21 closes |
| Revenue | Latest compatible annual SEC 10-K revenue, USD **millions** |
| Revenue growth | Change versus comparable prior annual SEC revenue |
| Net margin | Net income / revenue for matching annual start/end dates |
| Diluted EPS | Latest compatible annual SEC diluted EPS; basic EPS is fallback |
| Operating cash flow | Latest compatible annual SEC operating cash flow, USD millions |
| Operating cash flow/share | Annual operating cash flow / matching diluted weighted-average shares |
| Book value/share | Fiscal-year-end common equity / matching common shares outstanding |
| EPS target | EPS × business multiple |
| Cash-flow target | Operating cash flow/share × business multiple |
| Book-value target | Book value/share × book-value multiple |
| Valuation signals | Target price exceeds current Alpaca price; zero through three signals |
| Distance to high | Price difference from observed 365-calendar-day high |

The visible results table stays compact: symbol, company, current price, 20-day average volume,
and the EPS, operating-cash-flow, and book-value targets. CSV exports retain every collected and
calculated field, including dates, raw fundamentals, multiples, signals, and supporting metrics.

The financial values reflect filed reports, not current trading conditions. There is no options-chain screen or trade recommendation. Do not paste keys into chat, code, or exported data.

Business and book-value multiples are editable in the valuation panel. Changes immediately
recalculate loaded target prices, persist in browser storage, and require no provider request.
Refresh & Screen sends the selected multiples to the backend for complete-universe filtering.

Run `python3 -m unittest discover -s tests -v` to check bundled edge cases. Live provider screening requires your own keys and never exposes them to React.

Official documentation: [Alpaca assets](https://docs.alpaca.markets/us/docs/working-with-assets), [Alpaca data limits](https://docs.alpaca.markets/us/docs/about-market-data-api), [SEC Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [SEC ticker mapping](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
