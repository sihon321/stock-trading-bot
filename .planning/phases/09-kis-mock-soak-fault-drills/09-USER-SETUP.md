# Phase 9: User Setup Required

**Generated:** 2026-07-16
**Phase:** 09-kis-mock-soak-fault-drills
**Status:** Complete

The KIS mock credentials and mock account needed for the authenticated read-only compatibility checkpoint were configured locally. Secret values are not recorded here.

## Environment Variables

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [x] | `SOAK_KIS_MOCK__APP_KEY` | KIS Developers mock application credentials | Local `.env` only |
| [x] | `SOAK_KIS_MOCK__APP_SECRET` | KIS Developers mock application credentials | Local `.env` only |
| [x] | `SOAK_KIS_MOCK_ACCOUNT_CANO` | KIS mock account number | Local `.env` only |

## Verification

The authenticated probe completed against the KIS mock domain, published sanitized `KIS_OBSERVED` evidence, and performed zero order or cancellation POSTs. The operator explicitly approved the retained read-only profile on 2026-07-16.

Do not commit `.env` or copy credential values into planning artifacts, fixtures, logs, or chat.
