# Noodle Analytics

Noodle Analytics is a local stock-discovery application based on the project BRD and MVP baseline.
It screens active U.S. equities using Alpaca daily market data and SEC annual Company Facts. It
does not place trades or make automatic recommendations.

## Run with Coulson

Keep Docker Desktop and Coulson running, then open
[Noodle Analytics](http://noodle-analytics.localhost:18080).
Coulson starts the `noodle` Compose service on demand and stops it after its configured idle timeout.
The built React frontend and Python API share one container, listening on port `8765`.
Compose publishes it only at `127.0.0.1:8766`; Coulson provides the bookmark URL above.

Register this project once on another machine:

```sh
ln -s /absolute/path/to/Noodle_Analytics ~/.coulson/noodle-analytics
coulson scan
```

The `.coulson.toml` file selects Docker, `compose.yaml`, and the `noodle` service explicitly.
Use `coulson stop noodle-analytics` to stop it, or `coulson logs noodle-analytics` for diagnostics.
After changing source or dependencies, run `coulson stop noodle-analytics`,
`docker compose build`, then revisit the bookmark.

To unregister only this app, stop it, remove the matching
`~/.coulson/noodle-analytics` symlink, and run `coulson scan`. Keep the data volume.

## Run with Docker directly

Build and start the application:

```sh
docker compose up --build -d
```

Open <http://127.0.0.1:8766>. Stop it with `docker compose down`.

The Compose service stores caches and snapshots in the `noodle-data` volume. The image runs as a
non-root user and receives provider credentials only at runtime.
The project-scoped volume is `noodle-analytics_noodle-data` for both Coulson and direct Compose use.
Host files under `data/` remain separate and are not automatically imported.
Normal stop/start preserves the volume; avoid `docker compose down -v`, which deletes it.
The container does not restart automatically outside Coulson's managed lifecycle.

Both local Python commands and Docker Compose read provider settings from `.env`. Values already
present in the process environment take precedence during local execution. The React application
never receives these server-side credentials.

`ALPACA_DATA_FEED` defaults to `iex` for free Alpaca accounts. Set it to `sip` only when the
account's market-data entitlement supports SIP access.

`ALPACA_DATA_DELAY_MINUTES` defaults to `0`. Increase it only when the selected feed entitlement
requires delayed historical access.

`BUSINESS_MULTIPLE` defaults to `15` for EPS and operating-cash-flow target prices.
`BOOK_VALUE_MULTIPLE` defaults to `1.5` for the book-value target price. Both must be positive.
The valuation-data checkbox is enabled by default. Clear it for market-only screens that skip SEC.
The React valuation panel can override both defaults per screen. Preferences persist locally,
and changing them recalculates loaded results without contacting either provider.

To run without provider credentials, start the synthetic demo instead:

```sh
docker compose run --rm --service-ports noodle --host 0.0.0.0 --demo
```

Do not commit `.env`. Screening defaults to all eligible stocks. Set `NOODLE_SCREEN_LIMIT` to cap development runs.

## Project map

- `docs/product/` — product requirements and the original MVP operating baseline.
- `docs/architecture/` — system boundaries and workflow design.
- `docs/decisions/` — architecture decision records.
- `frontend/` — React and TypeScript browser application.
- `src/noodle_analytics/` — application code, organized by responsibility.
- `data/` — ignored runtime caches, snapshots, and exports.
- `scripts/` — local development and data-refresh entry points.
- `tests/` — unit tests, provider integration tests, and fixtures.

## Design constraints

- Use deterministic code for ingestion, calculations, filtering, and persistence.
- Keep Alpaca credentials and the SEC contact identity in environment variables.
- Preserve the last complete snapshot when a refresh fails.
- Represent unavailable financial values as missing, never zero.
- Treat valuation targets as deterministic research heuristics, not trade recommendations.
- Keep provider access server-side; screening operates on local snapshot data.
- Keep the Python runtime standard-library-only until intentionally revised.

## Frontend

The browser application uses React, TypeScript, Vite, and TanStack Table. During development,
Vite proxies `/api` requests to the local Python server on port `8765`.

```sh
cd frontend
npm install
npm run dev
```

For local frontend development, start the Python API separately on port `8765`. The production
container builds the React application and serves it from the Python process.

## Provider clients

- `providers/alpaca.py` retrieves active U.S. assets and paginated daily bars.
- `providers/sec.py` retrieves ticker mappings and cached annual Company Facts.
- `http_client.py` provides JSON parsing, timeouts, bounded retries, and backoff.

Every non-demo **Refresh & screen** action calls `POST /api/screen`. Alpaca snapshots update on
each call while assets and historical bars use local caches. Market filters run server-side.
SEC is skipped unless a financial filter is active; then only Alpaca survivors receive filing
checks. Company Facts downloads occur only for missing or newer annual filings.

## Suggested build order

1. Define domain records and metric calculations.
2. Extract Alpaca and SEC provider clients.
3. Implement cache and atomic snapshot storage.
4. Compose the refresh service.
5. Connect the React application to the local API.
6. Validate synthetic, missing-data, and live two-symbol flows.
