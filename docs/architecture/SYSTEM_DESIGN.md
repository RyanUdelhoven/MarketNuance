# System design

## Outcome

Let one local user run a freshness-aware, market-first screen while avoiding unnecessary downloads.

## Workflow map

| Stage | Input | Owner | Output | Validation | Failure path |
|---|---|---|---|---|---|
| Select universe | Alpaca assets | code | Eligible symbols | Status, class, symbol rules | Report exclusions |
| Fetch prices | Symbols, credentials, cache | code | Current snapshots and history | HTTP, schema, completeness | Abort refresh |
| Calculate market metrics | Daily bars | code | Price metrics | Window and date rules | Leave unavailable fields blank |
| Apply market criteria | Market metrics, thresholds | code | Alpaca survivors | Numeric and missing-value rules | Return no matches |
| Decide SEC stage | Financial criteria | code | Run or skip | Any SEC threshold active | Return market survivors |
| Map companies | SEC ticker index | code | Survivor CIKs | Daily cache, symbol normalization | Leave unmatched blank |
| Verify financials | Survivor CIKs | code | Filing metadata | SEC pacing | Abort non-404 failure |
| Fetch financials | Changed CIKs | code | Current Company Facts | Filing-date comparison | Reuse unchanged cache |
| Calculate financials | Company Facts | code | Annual metrics | Form, period, unit rules | Leave unavailable fields blank |
| Publish snapshot | Validated rows | code | Atomic local snapshot | Complete write before replace | Preserve prior snapshot |
| Choose thresholds | User criteria | human | Filter settings | Browser input constraints | Show actionable errors |
| Request fresh screen | Filter settings | code | Provider refresh request | One active refresh, local access | Label prior snapshot stale |
| Apply financial criteria | Verified facts, thresholds | code | Explainable candidates | Missing never passes | Preserve prior snapshot |
| Retain or export | Selected results | human | Watchlist or CSV | Explicit user action | No external side effect |

No AI stage is justified. Every refresh and screening decision follows auditable rules.

## Module boundaries

- `domain/` owns data shapes and pure financial or market calculations.
- `providers/` owns Alpaca and SEC protocols, retries, and response parsing.
- `services/` coordinates provider refresh before every non-demo screening workflow.
- `storage/` owns caches, snapshots, and atomic publication.
- `web/` owns Python HTTP routes and production asset serving.
- `frontend/` owns the React interface, browser state, filtering, sorting, and exports.

## Human authority

The user supplies screening criteria, decides which candidates matter, and initiates exports.
The application never recommends or executes a trade.

## Container runtime

A multi-stage Docker build compiles the React client with Node and copies only its static output
into a standard-library-only Python runtime. The final container runs without root privileges,
listens on port `8765`, and stores provider caches and snapshots under `/app/data`. Compose exposes
the service only through `127.0.0.1` so an outside host cannot trigger provider refreshes.

## Riskiest first slice

Refresh AAPL and MSFT using user-owned credentials. Verify market dates, SEC filing dates,
annual period matching, missing values, and preservation of an existing snapshot after failure.
