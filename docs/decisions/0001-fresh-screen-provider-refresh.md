# 0001 — Refresh providers on every screen

**Status:** superseded by the freshness-aware pipeline  
**Date:** 2026-09-14

## Context

The original MVP screened an existing local snapshot. The product now requires each non-demo
screen request to use the newest data available from Alpaca and SEC.

## Decision

React sends `POST /api/screen` with the selected criteria. The Python service allows one refresh
at a time, retrieves Alpaca assets and bars, retrieves the SEC ticker map and Company Facts,
atomically publishes the completed snapshot, and returns it. Screen-triggered SEC retrieval
bypasses the age cache. React applies the criteria after success.

## Consequences

- Screen results use data retrieved during that request.
- Screening latency includes provider pagination and SEC pacing.
- Failed requests preserve the prior snapshot but label it stale.
- Demo screening remains provider-free and conspicuously synthetic.
- Docker Compose binds to localhost to limit expensive refresh triggers.
- No AI stage is needed; the workflow remains deterministic.

## Superseding decision

Every screen still calls the local API and current Alpaca snapshots. Assets and historical bars
use durable caches. Market filters run before any SEC work. Financial criteria activate SEC
Submissions checks only for Alpaca survivors; Company Facts refresh only after a newer annual filing.
