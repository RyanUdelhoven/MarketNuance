# Application package

- `domain/` — records, validation, and pure metric calculations.
- `providers/` — Alpaca and SEC client adapters.
- `services/` — refresh and screening orchestration.
- `storage/` — SEC cache, snapshots, and atomic file publication.
- `web/` — local HTTP API, templates, and static browser assets.

Dependencies must point inward: providers, storage, and web may use domain code; domain code must
not depend on infrastructure.

