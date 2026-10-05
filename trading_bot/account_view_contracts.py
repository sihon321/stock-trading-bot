"""Credential-free schema contract for display-only broker balance evidence."""

ACCOUNT_VIEW_SCHEMA = {
    'account_view_metadata': {'owner', 'version', 'account_hash', 'target'},
    'account_view_attempts': {'attempt_id', 'observed_at', 'status', 'reason_code', 'snapshot_id'},
    'account_view_snapshots': {'snapshot_id', 'attempt_id', 'observed_at', 'available_cash',
        'total_evaluation', 'unrealized_value', 'valuation_complete', 'page_count'},
    'account_view_holdings': {'snapshot_id', 'ticker', 'quantity', 'orderable_quantity',
        'average_price', 'current_price', 'evaluation_amount', 'unrealized_profit', 'unrealized_return'},
}
ACCOUNT_VIEW_OWNER = 'account_view'
ACCOUNT_VIEW_VERSION = 1

# Only bounded codes, never the provider's raw exception/response body.
REFRESH_REASONS = {'COMPLETE', 'VALUATION_MISSING', 'INCOMPLETE_PAGES',
    'INVALID_BALANCE', 'AUTH_UNAVAILABLE', 'QUERY_UNAVAILABLE', 'REFRESH_FAILED'}
