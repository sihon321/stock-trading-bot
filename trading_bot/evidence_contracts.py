"""Read-only capability declarations, drift-checked against owner migrators.

Primary audit uses PRAGMA user_version and subset table/column capabilities.
Soak/controller schemas require exact owner tables and columns. Phase 11 uses
its independent phase11 metadata row; it does not own PRAGMA user_version.
No store connectors, migrations or trading configuration are imported here.
"""
from types import MappingProxyType

PRIMARY_AUDIT_SCHEMA_VERSION = 3
SOAK_SCHEMA_VERSION = 2
CONTROLLER_SCHEMA_VERSION = 1
PORTFOLIO_SCHEMA_VERSION = 3
PORTFOLIO_SCHEMA_OWNER = "phase11"

AUDIT_REPORT_SCHEMA = MappingProxyType({
    'runs': frozenset({
        'run_id', 'run_kind', 'started_at', 'status', 'target', 'trading_date_kst',
    }),
    'decisions': frozenset(('confidence', 'final_action', 'id', 'run_id', 'ticker')),
    'ticker_outcomes': frozenset({
        'final_order_state', 'id', 'order_intent_id', 'outcome_code', 'reason_code', 'run_id',
        'ticker',
    }),
    'order_events': frozenset(('event_type', 'id', 'order_intent_id')),
    'notification_attempts': frozenset({
        'delivery_status', 'failure_category', 'id', 'kind', 'observed_at', 'run_id', 'ticker',
    }),
})

PRIMARY_REPORT_SCHEMA = MappingProxyType({
    'runs': frozenset({
        'dry_run', 'finished_at', 'parent_run_id', 'policy_snapshot', 'provenance',
        'recovered_at', 'recovery_reason', 'run_id', 'run_kind', 'started_at', 'status',
        'target', 'trading_date_kst', 'trading_mode',
    }),
    'decisions': frozenset({
        'broker_order_id', 'confidence', 'correlation_id', 'created_at', 'current_price',
        'filled_qty', 'final_action', 'id', 'order_reason', 'override_reason', 'parse_error',
        'parsed_decision', 'requested_qty', 'risk_override', 'run_id', 'ticker',
    }),
    'ticker_outcomes': frozenset({
        'created_at', 'detail_json', 'failed_stage', 'final_order_state', 'id',
        'order_intent_id', 'outcome_code', 'reason_code', 'run_id', 'ticker',
    }),
    'order_events': frozenset({
        'broker_order_id', 'broker_status', 'detail_json', 'duplicate_of_intent_id',
        'event_type', 'filled_qty', 'id', 'observed_at', 'observer_run_id', 'order_intent_id',
        'origin_run_id', 'requested_qty', 'side', 'submission_id', 'ticker', 'unfilled_qty',
    }),
    'notification_attempts': frozenset({
        'delivery_status', 'detail_json', 'failure_category', 'id', 'kind', 'observed_at',
        'run_id', 'ticker',
    }),
})

SOAK_REPORT_SCHEMA = MappingProxyType({
    'soak_campaigns': frozenset({
        'accepted_profile_fingerprint', 'accepted_profile_version',
        'ambiguity_max_observations', 'ambiguity_policy_version',
        'ambiguity_poll_cadence_seconds', 'ambiguity_window_seconds',
        'availability_failure_budget', 'availability_failure_code',
        'availability_failures_used', 'campaign_id', 'campaign_kind', 'created_at',
        'credit_eligible', 'field_contract_version', 'safety_failure_code', 'state',
        'target_eligible_days',
    }),
    'soak_identity_receipts': frozenset({
        'account_suffix', 'campaign_id', 'detail_json', 'domain_class', 'id', 'observed_at',
        'policy_version', 'profile_version', 'receipt_id', 'target',
    }),
    'soak_days': frozenset({
        'campaign_id', 'credit_detail_json', 'credit_state', 'designated_at', 'id', 'run_id',
        'run_kind', 'terminal', 'trading_date',
    }),
    'soak_events': frozenset({
        'campaign_id', 'detail_json', 'drill_id', 'event_code', 'evidence_class', 'id',
        'observation_id', 'observed_at', 'order_intent_id', 'run_id', 'ticker',
    }),
    'soak_snapshots': frozenset({
        'campaign_id', 'completeness', 'detail_json', 'observed_at', 'run_id', 'snapshot_id',
        'stage', 'ticker',
    }),
    'soak_snapshot_orders': frozenset({
        'detail_json', 'id', 'observation_id', 'order_id', 'remaining_qty', 'snapshot_id',
        'status',
    }),
    'soak_snapshot_fills': frozenset({
        'detail_json', 'fill_id', 'id', 'observation_id', 'order_id', 'price', 'quantity',
        'snapshot_id',
    }),
    'soak_snapshot_holdings': frozenset({
        'average_price', 'detail_json', 'id', 'observation_id', 'quantity', 'snapshot_id',
        'ticker',
    }),
    'soak_snapshot_accounts': frozenset({
        'available_cash', 'detail_json', 'id', 'observation_id', 'snapshot_id', 'total_value',
    }),
    'soak_comparisons': frozenset({
        'campaign_id', 'comparison_id', 'detail_json', 'id', 'observed_at', 'order_intent_id',
        'remaining_order_terminal', 'run_id', 'snapshot_id', 'ticker', 'verdict',
    }),
    'soak_ambiguity_observations': frozenset({
        'campaign_id', 'detail_json', 'id', 'observation_id', 'observed_at', 'order_intent_id',
        'remaining_order_terminal', 'run_id', 'ticker', 'verdict',
    }),
    'soak_ticker_freezes': frozenset({
        'campaign_id', 'detail_json', 'freeze_id', 'freeze_kind', 'id', 'observed_at',
        'order_intent_id', 'prior_transition_id', 'release_evidence_id',
        'release_evidence_type', 'state', 'ticker',
    }),
    'soak_drill_links': frozenset({
        'campaign_id', 'detail_json', 'drill_id', 'evidence_class', 'id', 'link_id',
        'observed_at', 'order_intent_id', 'run_id', 'ticker', 'verdict',
    }),
})

CONTROLLER_REPORT_SCHEMA = MappingProxyType({
    'drill_contracts': frozenset({
        'campaign_id', 'drill_id', 'expected_containment_json', 'fault', 'injection_boundary',
        'policy_version', 'prepared_at', 'required_observations_json',
    }),
    'drill_commits': frozenset(('committed_at', 'drill_id', 'id')),
    'drill_observations': frozenset({
        'drill_id', 'evidence_class', 'facts_json', 'freeze_id', 'id', 'observation_type',
        'observed_at', 'order_intent_id', 'primary_run_id', 'reconciliation_id', 'ticker',
    }),
    'drill_verdicts': frozenset(('detail_json', 'drill_id', 'finalized_at', 'id', 'verdict')),
})

PORTFOLIO_REPORT_SCHEMA = MappingProxyType({
    'portfolio_schema_metadata': frozenset(('owner', 'version')),
    'portfolio_snapshots': frozenset({
        'account_scope_hash', 'available_cash', 'balance_page_count', 'completeness',
        'cycle_id', 'daily_page_count', 'observation_id', 'observed_at',
        'previous_trading_date_kst', 'reason_code', 'snapshot_id', 'total_evaluation',
        'trading_date_kst',
    }),
    'portfolio_holdings': frozenset({
        'average_price', 'orderable_quantity', 'snapshot_id', 'ticker', 'total_quantity',
    }),
    'portfolio_orders': frozenset({
        'cancelled_quantity', 'filled_quantity', 'limit_price', 'order_date', 'order_id',
        'order_time', 'ordered_quantity', 'original_order_id', 'rejected_quantity',
        'remaining_quantity', 'side', 'snapshot_id', 'status', 'ticker',
    }),
    'portfolio_fills': frozenset({
        'fill_id', 'order_id', 'price', 'quantity', 'snapshot_id', 'ticker',
    }),
    'portfolio_divergences': frozenset({
        'code', 'id', 'order_intent_id', 'severity', 'snapshot_id', 'ticker',
    }),
    'daily_evaluations': frozenset({
        'account_scope_hash', 'canonical_input', 'canonical_input_hash', 'evaluation_id',
        'finalized_at', 'provenance_json', 'started_at', 'status', 'ticker',
        'trading_date_kst',
    }),
    'daily_evaluation_events': frozenset({
        'action', 'confidence', 'detail_json', 'evaluation_id', 'event_type', 'id',
        'observed_at', 'reason_code',
    }),
    'watch_iterations': frozenset({
        'cycle_id', 'iteration_id', 'snapshot_id', 'started_at', 'terminal_status',
    }),
    'watch_observations': frozenset({
        'detail_json', 'id', 'iteration_id', 'observed_at', 'state_code',
    }),
    'transition_states': frozenset({
        'account_scope_hash', 'active', 'broker_subject_id', 'duration_seconds',
        'event_family', 'first_observed_at', 'id', 'last_notification_status',
        'last_observed_at', 'occurrence_count', 'severity', 'state_code', 'state_identity',
        'ticker',
    }),
    'transition_observations': frozenset({
        'detail_json', 'id', 'observed_at', 'severity', 'state_code', 'state_identity',
    }),
    'transition_notifications': frozenset({
        'delivery_status', 'event_code', 'failure_category', 'id', 'observed_at', 'severity',
        'state_identity', 'text',
    }),
    'mutation_leases': frozenset({
        'account_scope_hash', 'command', 'cycle_id', 'heartbeat_at', 'owner_token', 'pid',
        'started_at', 'state',
    }),
    'mutation_lease_events': frozenset({
        'account_scope_hash', 'detail_json', 'event_type', 'from_state', 'id', 'observed_at',
        'observer_cycle_id', 'origin_cycle_id', 'owner_token', 'to_state',
    }),
})

