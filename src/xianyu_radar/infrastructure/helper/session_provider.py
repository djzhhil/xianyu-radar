"""One bounded account operation; only status metadata survives its lifetime."""

from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock

from xianyu_radar.infrastructure.goofish.errors import HelperError, error_kind
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.helper.client import HelperClient, HelperConfig

_guard = Lock()
_locks: dict[tuple[str, str], Lock] = {}
_states: dict[tuple[str, str], dict] = {}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _record(config: HelperConfig, **values) -> None:
    with _guard:
        _states.setdefault((config.base_url, config.account_id), {}).update(values)


def provider_status() -> dict:
    try:
        config = HelperConfig.from_env()
    except HelperError as exc:
        return {"source": "Helper", "ok": False, "configured": False, "connection_status": "unconfigured",
                "account_id": None, "hint": str(exc), "last_error_kind": exc.kind}
    with _guard:
        state = dict(_states.get((config.base_url, config.account_id), {}))
    return {"source": "Helper", "configured": True, "account_id": config.account_id,
            "ok": state.get("connection_status") == "connected", "connection_status": "unchecked", **state}


@contextmanager
def session_operation():
    config = HelperConfig.from_env()
    key = (config.base_url, config.account_id)
    with _guard:
        lock = _locks.setdefault(key, Lock())
    # Lock ownership and release stay inside the same API/CLI call, not a
    # FastAPI generator dependency which may resume on another worker thread.
    with lock:
        helper = HelperClient(config)
        session = None
        try:
            jar, version = helper.snapshot()
            _record(config, connection_status="connected", last_fetch_at=timestamp(), last_error_kind=None)

            def submit(batches):
                try:
                    result = helper.updates(session.credential_version, batches)
                except HelperError as exc:
                    _record(config, connection_status="error", last_error_kind=exc.kind)
                    raise
                _record(config, last_submit_at=timestamp(), runtime_sync_status=result["runtime_sync_status"])
                return result

            session = Session(source="Helper", jar=jar, credential_version=version,
                              account_id=config.account_id, submit_updates=submit)
            yield session
        except Exception as exc:
            _record(config, last_error_kind=error_kind(exc))
            if isinstance(exc, HelperError):
                _record(config, connection_status="error")
            raise
        finally:
            if session is not None:
                if session.stop_kind:
                    _record(config, last_error_kind=session.stop_kind)
                session.close()
            helper.close()
