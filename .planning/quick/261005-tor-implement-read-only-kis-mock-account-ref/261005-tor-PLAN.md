---
quick_id: 261005-tor
mode: quick
status: planned
---

# Account display refresh and saved valuation support

Approved scope: implement the four account improvements discussed with the owner, including a query-only refresh worker, persisted holding valuations, last complete holdings outside today's history filter, and clear failure/missing/stale explanations. Execute inline under GSD quick fallback.

1. Add a dedicated mock-only account-view storage owner and protected refresh settings/CLI. Reuse KIS balance pagination and token caching through a transport permitting only OAuth and balance GET, without LLM/trading composition. Store sanitized scalar values and every refresh outcome; never rewrite legacy trading evidence or recovery state.
2. Expand balance field allowlists using KIS official examples. Persist nullable current price, evaluation, signed P/L and percent return; incomplete pagination/invalid identities cannot replace a complete snapshot. No fabricated prices/P/L or real-mode selection.
3. Add credential-free saved account-view reader contracts, exact snapshot/holding drill-down and scope validation. Prefer the display source for account/holding pages; keep legacy risk/order sources. Latest holdings are independent of today's run-history filter, with explicit observation/staleness/failure labels.
4. Add targeted normalization, transport prohibition, storage/failure retention, scope and web route regression coverage. Run affected existing tests and appropriate integration checks.
5. Register protected runtime config/source, run one real mock balance inquiry, then start periodic refresh only after the successful result is checked. Restart web/observer only as needed for new resource contracts. Verify authenticated HTTPS and preserved trading DBs/observer; document any externally blocked KIS query honestly.
6. Add the authorized account-display follow-up to ROADMAP/REQUIREMENTS and document completed implementation separately from deployment. Update quick SUMMARY/STATE, commit/push using existing message style.
