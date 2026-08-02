"""In-memory action audit log for this process. Deliberately not durable - Phase 6
(incident event store) will persist the full decision trail in Postgres; until then
this is enough to support the approval workflow and GET /actions within one run of
the engine."""

from .models import RemediationAction

_actions: dict[str, RemediationAction] = {}
_order: list[str] = []


def add(action: RemediationAction) -> None:
    _actions[action.id] = action
    _order.append(action.id)


def get(action_id: str) -> RemediationAction | None:
    return _actions.get(action_id)


def update(action: RemediationAction) -> None:
    _actions[action.id] = action


def list_all() -> list[RemediationAction]:
    return [_actions[aid] for aid in reversed(_order)]
