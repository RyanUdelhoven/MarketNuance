# Business Requirements Document — Stock Discovery MVP

**Version 0.4 · 2026-09-14 · Owner: Ryan · Status: active build baseline**

## Goal

Find new stock candidates for discretionary stock and options trading without a recurring data subscription. In a local browser, Ryan chooses price, liquidity, momentum and annual financial requirements, clicks **Refresh & screen**, and receives qualifying tickers calculated from the newest data available from the configured provider APIs. This app never places trades.

**Budget and sources:** $0/month. One free Alpaca paper account supplies available U.S. assets and market data; SEC EDGAR supplies annual company financial disclosures without a key. Every non-demo screen request checks current Alpaca market state. The service calls SEC only when financial criteria are active, and only for candidates surviving Alpaca filters.

## Functional requirements

| ID | Requirement | Acceptance |
|---|---|---|
| R1 | Import available U.S. active equities and daily bars from Alpaca. | No separate symbol-directory service or paid plan is needed. |
| R2 | Join SEC standardized annual Company Facts by ticker/CIK. | Show latest compatible annual revenue, revenue growth, net margin and filing date; missing is blank. |
| R3 | Fresh, explicit front-end screening. | Clicking Refresh & screen updates Alpaca, filters market metrics, conditionally verifies SEC survivors, then publishes atomically. |
| R4 | Explain results. | Compact table shows price, 20-day volume, and three targets; complete metrics remain exportable. |
| R5 | Retain candidates. | Watchlist persists in the browser; filtered list exports as CSV. |
| R6 | Safe evaluation and refresh. | Synthetic demo is conspicuous; concurrent refreshes are rejected; an unsuccessful refresh preserves and labels the prior snapshot as stale. |
| R7 | Deterministic valuation targets. | Calculate EPS, cash-flow and book-value targets with editable, persistent multiples; expose numeric filters and comparison signals. |

## Definitions and limits

- Average volume uses 20 daily bars. Return uses 21 closes to measure 20 trading sessions.
- Default market filters are $15 minimum, $30 maximum, and 10,000 average daily shares.
- Every filter label explains its source, formula, period, or default through an information tooltip.
- Observed high uses daily highs from the latest 365 calendar days; newly listed assets have less history.
- Revenue uses one standard U.S.-GAAP annual tag from a 10-K/10-K/A with a roughly year-long reporting interval, in USD millions.
- Revenue growth compares with a roughly year-earlier comparable full-year period. Net margin matches revenue and earnings by start/end date.
- SEC and price dates differ. Nonstandard tags, foreign issuer filings and unmatched tickers may leave financial values blank. Missing never means zero.
- Alpaca's `us_equity` class contains some ETFs and other instruments. Name-based exclusion is imperfect; this is Alpaca's eligible universe, not every U.S. common stock.
- Screening defaults to the full eligible universe. `NOODLE_SCREEN_LIMIT` can restore a temporary cap.
- The default IEX request uses no intentional delay. A configured delay applies only when required by the selected Alpaca entitlement.
- Historical bars and assets persist locally; snapshots update current market state on every screen.
- Active SEC filters trigger filing checks only for Alpaca survivors. Unchanged facts remain cached.
- SEC-free screens require no SEC request or SEC identity configuration.
- EPS uses the latest compatible annual diluted per-share fact, with basic EPS as fallback.
- Operating cash flow per share matches annual cash flow with diluted weighted-average shares.
- Book value per share matches fiscal-year-end equity with fiscal-year-end common shares.
- EPS and cash-flow targets use `BUSINESS_MULTIPLE`, defaulting to 15.
- Book-value target uses `BOOK_VALUE_MULTIPLE`, defaulting to 1.5.
- Users can override both multiples per screen; browser preferences persist locally.
- Multiple changes recalculate loaded target prices without provider requests.
- A target receives `BUY` when it exceeds the current Alpaca price.
- Valuation retrieval is enabled by default and can be disabled to skip SEC.

## Nonfunctional requirements

Single-user local browser; no third-party Python packages; credentials remain server-side; SEC requests identify the user and remain conservatively paced; every screen calls local `POST /api/screen`; the service rejects overlapping refreshes and remains localhost-bound through Docker Compose.

## Excluded for this release

Options-chain screening, Greeks, execution spreads, real-time alerts, automatic recommendations, trading orders, portfolio import, deep valuation, quarterly financial normalization and definitive security-type classification.

## Definition of done

Using user-owned credentials, verify market-only screens skip SEC. Activate a financial filter and verify Alpaca filters first, SEC checks only survivors, unchanged Company Facts remain cached, and provider status appears in React. Verify failures preserve the prior snapshot.

Official sources: [Alpaca assets](https://docs.alpaca.markets/us/reference/get-v2-assets-1), [Alpaca market-data access](https://docs.alpaca.markets/us/docs/about-market-data-api), [SEC Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [SEC ticker association](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
