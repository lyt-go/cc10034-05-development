"""访问审计领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。

除通用逐条审计记录外，登记成功的审计事件会镜像一份到「会话时间线」领域，
让通过通用登记接口或事件上报接口进来的事件都能按会话复核；镜像失败不影响
通用登记主流程。本类也暴露会话时间线/事件补送的委托方法，方便服务层直接调用。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService


class AccessAuditService(BaseModuleService):
    MODULE = "access_audit"
    ENTITY = "审计记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["记录编号", "访问主体", "目标资源", "访问操作", "访问时间", "请求IP", "访问结果", "敏感等级"]
    REQUIRED_FIELDS = ["记录编号", "访问主体", "目标资源"]
    STATUS_ORDER = ["已记录", "需复核", "已异常"]
    ACTION_RULES = {"标记复核": "需复核", "标记异常": "已异常"}
    NEGATIVE_ACTIONS = []

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        entry, missing = super().create_entry(values)
        if entry is not None and not missing:
            self._mirror_to_session_timeline(values, entry)
        return entry, missing

    # -------------------------------------------------------- 会话时间线委托
    @staticmethod
    def list_sessions() -> list[dict[str, Any]]:
        from app.services.session_review import session_review_service
        return session_review_service.list_sessions()

    @staticmethod
    def session_timeline(session_ref: Any) -> list[dict[str, Any]]:
        from app.services.session_review import session_review_service
        return session_review_service.timeline(session_ref)

    @staticmethod
    def report_session_event(payload: dict[str, Any]):
        from app.services.session_review import session_review_service
        return session_review_service.report_event(payload)

    @staticmethod
    def _mirror_to_session_timeline(values: dict[str, Any], entry: dict[str, Any]) -> None:
        try:
            from app.services.session_review import session_review_service

            payload = dict(values)
            # 用通用记录编号作为幂等键，重复登记同一编号时时间线只显示一次。
            payload.setdefault("event_uid", values.get("记录编号") or entry.get("记录编号"))
            session_ref = values.get("会话编号") or values.get("session_id")
            if session_ref:
                payload["session_id"] = session_ref
            else:
                # 按 请求IP / 访问主体 关联原会话；匹配不上且只有一个会话时由领域层归入。
                for session in session_review_service.sessions:
                    if values.get("请求IP") and values["请求IP"] == session.get("请求IP"):
                        payload["session_id"] = session["session_uid"]
                        break
                    if values.get("访问主体") and values["访问主体"] == session.get("访问主体"):
                        payload["session_id"] = session["session_uid"]
                        break
            session_review_service.report_event(payload)
        except Exception:
            # 会话时间线是增强能力，绝不能让通用登记接口因此失败。
            pass
