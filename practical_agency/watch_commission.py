"""Public adapter boundary for externally verified watch-commission@1 records."""
from practical_agency.watch_commission_core import (
    CommissionIntegrationError,
    ExternalCommissionResult,
    Verifier,
    WatchExecutionAdapter,
    accept_external_commission,
    exercise_kill_switch,
    prepare_disabled,
    retain_commission,
)
from practical_agency.watch_commission_runtime import (
    disable_commissions_for_revocation,
    handle_crossing_event,
)

__all__ = [
    "CommissionIntegrationError",
    "ExternalCommissionResult",
    "Verifier",
    "WatchExecutionAdapter",
    "accept_external_commission",
    "disable_commissions_for_revocation",
    "exercise_kill_switch",
    "handle_crossing_event",
    "prepare_disabled",
    "retain_commission",
]
