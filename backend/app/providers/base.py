from __future__ import annotations


class ProviderNotConfigured(RuntimeError):
    """운영 provider 에 필요한 키/계약이 아직 없는 경우."""


class ProviderError(RuntimeError):
    """외부 provider 호출 실패 (재시도 가능)."""


# 선택된 provider 와 mock 대체 여부를 Admin 화면에 보여주기 위한 기록
PROVIDER_STATUS: dict[str, dict] = {}


def note(kind: str, requested: str, active: str, reason: str = "") -> None:
    PROVIDER_STATUS[kind] = {"requested": requested, "active": active, "fallback": requested != active, "reason": reason}
