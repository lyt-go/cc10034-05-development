"""异常检测领域服务：异常规则配置 + 告警会话复核。

规则本身的字段、状态和动作来自业务配置；告警（alert）的会话时间线、
确认/重开复核逻辑委托给独立的 session_review 领域服务。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService


class AnomalyDetectService(BaseModuleService):
    MODULE = "anomaly_detect"
    ENTITY = "异常规则"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["规则编号", "检测维度", "检测算法", "阈值上限", "时间窗口", "告警级别", "规则版本", "触发次数"]
    REQUIRED_FIELDS = ["规则编号", "检测维度", "检测算法"]
    STATUS_ORDER = ["草稿", "待验证", "已启用", "已停用"]
    ACTION_RULES = {"提交验证": "待验证", "启用规则": "已启用", "停用规则": "已停用"}
    NEGATIVE_ACTIONS = ["停用规则"]

    # ------------------------------------------------------------ 告警复核委托
    @staticmethod
    def list_alerts() -> list[dict[str, Any]]:
        from app.services.session_review import session_review_service
        return session_review_service.list_alerts()

    @staticmethod
    def alert_detail(alert_ref: Any) -> dict[str, Any]:
        from app.services.session_review import session_review_service
        return session_review_service.alert_detail(alert_ref)

    @staticmethod
    def confirm_alert(alert_ref: Any, conclusion: str = "", reviewer: str = ""):
        from app.services.session_review import session_review_service
        return session_review_service.confirm_alert(alert_ref, conclusion, reviewer)

    @staticmethod
    def reopen_alert(alert_ref: Any, reason: str = "", reviewer: str = ""):
        from app.services.session_review import session_review_service
        return session_review_service.reopen_alert(alert_ref, reason, reviewer)
