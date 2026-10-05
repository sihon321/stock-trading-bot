---
status: resolved
trigger: "알람에 문제가 있는거 같은데 확인해줘"
created: 2026-10-05
updated: 2026-10-05
---

# Alert source read failures

## Symptoms

Expected: configured independent observer reads registered saved mock evidence and shows accurate incident and delivery status.
Actual: observer RUNNING, two Discord reminders DELIVERED, two historic producer attempts FAILED, two earlier unconfigured observer attempts DISABLED. Audit and soak source reads fail; checkpoint remains unset. Owner-specific visible symptom requested asynchronously.
Reproduction: read-only `OperatorEvidenceService.observe_alert_sources()` on the registered deployment reports audit INVALID_SOURCE_DATA and soak INVALID_SOURCE_ID.

## Current Focus

hypothesis: confirmed date identity rejection, blocked healthy-source pagination, source availability recovery timestamp mismatch and campaign creation misused as latch occurrence time.
next_action: none; fixes verified and deployed, historical audit completeness remains explicitly unavailable.

## Evidence

- Observer fresh heartbeat, no lifecycle failure; two real observer-owned reminder receipts DELIVERED. Discord transport is working.
- Four active episodes: portfolio BROKER_TRUTH_FAILED and RECONCILIATION_UNRESOLVED; audit/soak source availability warnings.
- Read-only source inspection reports INVALID_SOURCE_DATA/INVALID_SOURCE_ID, preserving unavailable state and preventing complete checkpoint advancement.
- No acknowledgement exists. CRITICAL reminders recur every 30 minutes by existing policy; a successful send does not recover a trading incident.
- Five synthetic regressions failed before fixes. After fixes, 46 web-evidence/observer tests passed. Read-only deployment projection now reports soak OK and traverses 100 + 34 + 0 facts; healthy partitions advance while the audit source remains correctly unavailable.

## Fix

- Valid calendar-date components in typed public identifiers retain identity; standalone account-shaped numbers, credential tokens and invalid dates retain existing redaction/rejection.
- Reader omits failed partitions from its progress calculation and explicitly certifies a partial checkpoint that preserves failed stream positions. Observer accepts only that explicit healthy progress; ordinary incomplete/expectation-failed batches still cannot advance.
- A successful current read can recover source availability using its query timestamp without renewing the historical producer observation time.
- Campaign safety latches use saved latch events, never campaign creation as an invented observation time.
- Historical audit provenance/scope failures remain fail-safe; no saved data rewrite or broker recovery is introduced.
- Discord messages include source, saved subject and KST observation time; reminders explain acknowledgement so separate historical incidents are distinguishable.

## Verification and deployment

- 746 related web/alert/service tests passed. Supplemental recovery/identity regressions passed, then the final alert/web-evidence suite passed 92 tests after message enrichment. Account-shaped numbers, invalid dates, secret tokens, failed-partition recovery and reads finishing after scan start are covered.
- Actual read-only projection traverses 100 + 34 + 0 records. Soak/portfolio/controller are readable; historical audit INVALID_SOURCE_DATA remains denied. Healthy partition positions now persist without consuming the failed audit partition.
- Protected existing processes were stopped gracefully and restarted. Current web PID 99256 and observer PID 99863 are tracked externally. Observer RUNNING, no lifecycle failure. A second observer restart did not replay any finalized notification.
- Deployment saved 14 newly detected observer occurrence deliveries and one source-read recovery delivery as DELIVERED; two earlier reminder deliveries remain DELIVERED. Old producer FAILED and initial unconfigured DISABLED attempts were preserved.
- Active saved risks: seven campaign safety latches, seven ticker freezes, two portfolio critical states and one audit source-read warning. Soak source availability warning recovered; no broker freeze/latch was released by this work.
- Real authenticated HTTPS alerts/detail pages render the stored evidence. Original audit/soak/controller DB SHA256 digests remain unchanged; webhook absent from observer log and repository changes.

The remaining audit warning is missing/invalid historical provenance, not a failing Discord transport. No fabricated identity or source migration was used to hide it. CRITICAL reminders remain the documented 30-minute policy until current-revision acknowledgement or same-subject recovery proof.

## Constraints

Preserve source DBs, mock scope restrictions, safety freezes/latches, immutable finalized delivery receipts and sensitive-data redaction. Never infer broker recovery or healthy current trading from historical data. Continue inline under the GSD skill fallback; no subagents requested.
