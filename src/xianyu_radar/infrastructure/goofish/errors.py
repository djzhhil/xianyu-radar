"""Non-sensitive failure categories shared by all online operations."""

STOP_KINDS = frozenset({
    "auth", "token", "verification_required", "rate_limit", "helper_config",
    "helper_auth", "helper_permission", "helper_account", "helper_unavailable",
    "cookie_snapshot_unavailable", "helper_contract", "credential_conflict",
    "cookie_update_unknown", "cookie_update_rejected", "cookie_update_limit",
})


class AuthError(Exception):
    kind = "auth"


class HelperError(Exception):
    def __init__(self, kind: str, message: str, *, status: int = 503):
        super().__init__(message)
        self.kind = kind
        self.status = status


def error_kind(exc: Exception) -> str:
    kind = getattr(exc, "kind", None)
    if kind:
        return kind
    # Compatibility for offline fixtures constructing the existing MtopError.
    blob = f"{exc} {getattr(exc, 'ret', '')}".lower()
    if "user_validate" in blob or "x5sec" in blob:
        return "verification_required"
    if "rgv587" in blob or "挤爆" in blob or "稍后重试" in blob:
        return "rate_limit"
    return "network"
