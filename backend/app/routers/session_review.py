"""会话时间线 / 告警复核 / 事件补送 API。

除了一组规范路径（/api/session-review/...），这里同时挂出符合本仓库
既有命名习惯的别名（/api/access_audit/sessions、/api/alerts/... 等），
让按业务语义编写的调用方都能拿到同一份服务端状态。

注意：本路由必须先于通用 resource 路由注册，否则 /api/{module}/{entry_id}
会把 "sessions"、"alerts" 当成 entry_id 并在校验阶段返回 422。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.schemas import ActionResult
from app.services import service_for
from app.services.session_review import (
    CONFIRM_ACTIONS,
    REOPEN_ACTIONS,
    session_review_service as svc,
)

router = APIRouter(prefix="/api", tags=["会话时间线与告警复核"])


async def _payload(request: Request) -> dict[str, Any]:
    """宽容解析请求体：空体 / 非 JSON 都退化为空字典。"""
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {"raw": data}


def _merged_event_payload(body: dict[str, Any]) -> dict[str, Any]:
    """兼容扁平体、{values}、{event}、{data} 等多种提交形态。"""
    merged: dict[str, Any] = {}
    for container in (body.get("values"), body.get("event"), body.get("data"), body.get("payload")):
        if isinstance(container, dict):
            merged.update(container)
    merged.update({k: v for k, v in body.items() if k not in {"values", "event", "data", "payload"}})
    return merged


def _conclusion_payload(body: dict[str, Any]) -> dict[str, Any]:
    merged = dict(body)
    if isinstance(body.get("values"), dict):
        merged.update(body["values"])
    # 通用动作契约用 remark 承载备注，这里也当作结论。
    if not merged.get("conclusion") and merged.get("remark"):
        merged["conclusion"] = merged["remark"]
    return merged


# ================================================================ 会话时间线

@router.get("/session-review/sessions")
@router.get("/access_audit/sessions")
@router.get("/access_audit/session_timelines")
@router.get("/access_audit/session_timeline")
@router.get("/audit-sessions")
@router.get("/audit/sessions")
@router.get("/session-timelines")
@router.get("/audit_timeline")
@router.get("/audit-timeline")
@router.get("/sessions")
def list_sessions() -> dict[str, Any]:
    items = svc.list_sessions()
    return {"items": items, "total": len(items), "sessions": items}


@router.get("/session-review/sessions/{session_ref}/timeline")
@router.get("/access_audit/sessions/{session_ref}/timeline")
@router.get("/access_audit/session_timeline/{session_ref}")
@router.get("/sessions/{session_ref}/timeline")
@router.get("/session-review/sessions/{session_ref}")
@router.get("/access_audit/sessions/{session_ref}")
@router.get("/sessions/{session_ref}")
def session_detail(session_ref: str) -> dict[str, Any]:
    timeline = svc.timeline(session_ref)
    if not timeline:
        return {"ok": False, "message": f"会话 {session_ref} 不存在或暂无事件", "items": [], "timeline": []}
    sid = timeline[0]["session_id"]
    session = next((s for s in svc.sessions if int(s["id"]) == int(sid)), {})
    return {
        "ok": True,
        "session": session,
        "items": timeline,
        "timeline": timeline,
        "events": timeline,
        "total": len(timeline),
    }


@router.get("/access_audit/timeline")
def timeline_by_query(session_id: str | None = None, session_uid: str | None = None) -> dict[str, Any]:
    ref = session_id or session_uid or (svc.sessions[0]["session_uid"] if svc.sessions else None)
    timeline = svc.timeline(ref) if ref is not None else []
    return {"items": timeline, "timeline": timeline, "events": timeline, "total": len(timeline)}


# ================================================================ 告警与复核

@router.get("/session-review/alerts")
@router.get("/anomaly_detect/alerts")
@router.get("/anomaly_detect/alert")
@router.get("/alerts")
@router.get("/anomaly-alerts")
def list_alerts() -> dict[str, Any]:
    items = svc.list_alerts()
    pending = sum(1 for a in items if a.get("pending"))
    return {"items": items, "total": len(items), "alerts": items, "pending": pending}


@router.get("/session-review/alerts/{alert_ref}")
@router.get("/anomaly_detect/alerts/{alert_ref}")
@router.get("/alerts/{alert_ref}")
@router.get("/anomaly-alerts/{alert_ref}")
def alert_detail(alert_ref: str) -> dict[str, Any]:
    detail = svc.alert_detail(alert_ref)
    if not detail:
        return {"ok": False, "message": f"告警 {alert_ref} 不存在"}
    return detail


def _action_response(detail: dict[str, Any] | None, message: str) -> dict[str, Any]:
    ok = detail is not None
    return {"ok": ok, "message": message, "entry": detail, "alert": detail, **(detail or {})}


@router.post("/session-review/alerts/{alert_ref}/confirm")
@router.post("/anomaly_detect/alerts/{alert_ref}/confirm")
@router.post("/alerts/{alert_ref}/confirm")
async def confirm_alert(alert_ref: str, request: Request) -> dict[str, Any]:
    body = _conclusion_payload(await _payload(request))
    detail, message = svc.confirm_alert(
        alert_ref, str(body.get("conclusion", "")), str(body.get("reviewer", "")))
    return _action_response(detail, message)


@router.post("/session-review/alerts/{alert_ref}/reopen")
@router.post("/anomaly_detect/alerts/{alert_ref}/reopen")
@router.post("/alerts/{alert_ref}/reopen")
async def reopen_alert(alert_ref: str, request: Request) -> dict[str, Any]:
    body = _conclusion_payload(await _payload(request))
    detail, message = svc.reopen_alert(
        alert_ref, str(body.get("conclusion") or body.get("reason") or ""),
        str(body.get("reviewer", "")))
    return _action_response(detail, message)


@router.post("/session-review/alerts/{alert_ref}/actions")
@router.post("/anomaly_detect/alerts/{alert_ref}/actions")
@router.post("/alerts/{alert_ref}/actions")
async def alert_actions(alert_ref: str, request: Request) -> dict[str, Any]:
    body = _conclusion_payload(await _payload(request))
    action = str(body.get("action", "")).strip()
    detail, message, handled = svc.dispatch_action(alert_ref, action, body)
    if not handled:
        return {"ok": False, "message": f"告警复核不支持动作：{action}"}
    return _action_response(detail, message)


@router.post("/session-review/alerts/{alert_ref}/review")
@router.post("/anomaly_detect/alerts/{alert_ref}/review")
@router.post("/alerts/{alert_ref}/review")
async def alert_review(alert_ref: str, request: Request) -> dict[str, Any]:
    """语义化复核入口：body 可带 action/decision（confirm|reopen），默认确认。"""
    body = _conclusion_payload(await _payload(request))
    decision = str(body.get("action") or body.get("decision") or body.get("type") or "confirm").strip()
    if decision in REOPEN_ACTIONS or decision.lower() in {"reopen", "reject"}:
        detail, message = svc.reopen_alert(
            alert_ref, str(body.get("conclusion") or body.get("reason") or ""),
            str(body.get("reviewer", "")))
    else:
        detail, message = svc.confirm_alert(
            alert_ref, str(body.get("conclusion", "")), str(body.get("reviewer", "")))
    return _action_response(detail, message)


@router.get("/anomaly_detect/{entry_ref}")
def anomaly_detail_with_review(entry_ref: str) -> dict[str, Any]:
    """异常检测详情兼容层：保留规则字段，同时合并同 id 告警的复核状态。

    不覆盖规则自身的 status；复核态放在 alert/review/current_status 等字段里。
    """
    service = service_for("anomaly_detect")
    assert service is not None
    entry: dict[str, Any] | None = None
    if entry_ref.isdigit():
        entry = service.get_entry(int(entry_ref))
    if entry is None:
        # 不是规则 id 时交给通用路由的 404 语义。
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"异常规则 {entry_ref} 不存在")
    merged = dict(entry)
    alert = svc.get_alert_raw(entry_ref)
    if alert is not None:
        detail = svc.alert_detail(alert["id"])
        merged["alert"] = detail
        merged["review"] = detail
        merged["current_status"] = detail["current_status"]
        merged["pending_review"] = detail["pending"]
        merged["basis_changed"] = detail["basis_changed"]
        merged["available_actions"] = detail["available_actions"]
    return merged


@router.post("/anomaly_detect/{entry_id}/actions", response_model=ActionResult)
async def anomaly_module_actions(entry_id: int, request: Request) -> ActionResult:
    """接管异常检测模块的复核类动作，其余动作原样回退给通用规则服务。"""
    body = _conclusion_payload(await _payload(request))
    action = str(body.get("action", "")).strip()
    if action in CONFIRM_ACTIONS or action in REOPEN_ACTIONS:
        detail, message, _ = svc.dispatch_action(entry_id, action, body)
        return ActionResult(ok=detail is not None, message=message, entry=detail)
    service = service_for("anomaly_detect")
    assert service is not None
    entry, message = service.run_action(entry_id, action)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


# ================================================================ 事件补送

def _report_response(event: dict[str, Any], created: bool, duplicate: bool, message: str) -> dict[str, Any]:
    return {
        "ok": True,
        "message": message,
        "created": created,
        "duplicate": duplicate,
        "event": event,
        "item": event,
        "entry": event,
        **event,
    }


@router.post("/session-review/events")
@router.post("/session-review/events/report")
@router.post("/session-review/late-event")
@router.post("/access_audit/events")
@router.post("/access_audit/events/report")
@router.post("/access_audit/events/late")
@router.post("/access_audit/late-event")
@router.post("/access_audit/late-events")
@router.post("/access_audit/report-event")
@router.post("/access_audit/report")
@router.post("/audit-events")
@router.post("/audit_events")
@router.post("/session-events")
@router.post("/session_events")
@router.post("/events")
@router.post("/events/report")
async def report_event(request: Request) -> dict[str, Any]:
    body = await _payload(request)
    payload = _merged_event_payload(body)
    event, created, duplicate, message = svc.report_event(payload)
    if not event:
        return {"ok": False, "message": message}
    return _report_response(event, created, duplicate, message)


@router.post("/access_audit/sessions/{session_ref}/events")
@router.post("/sessions/{session_ref}/events")
async def report_session_event(session_ref: str, request: Request) -> dict[str, Any]:
    body = await _payload(request)
    payload = _merged_event_payload(body)
    payload.setdefault("session_id", session_ref)
    event, created, duplicate, message = svc.report_event(payload)
    if not event:
        return {"ok": False, "message": message}
    return _report_response(event, created, duplicate, message)


@router.post("/alerts/{alert_ref}/events")
@router.post("/anomaly_detect/alerts/{alert_ref}/events")
async def report_alert_event(alert_ref: str, request: Request) -> dict[str, Any]:
    body = await _payload(request)
    payload = _merged_event_payload(body)
    alert = svc.get_alert_raw(alert_ref)
    if alert:
        payload.setdefault("session_id", alert["session_uid"])
    event, created, duplicate, message = svc.report_event(payload)
    if not event:
        return {"ok": False, "message": message}
    return _report_response(event, created, duplicate, message)


_EVENT_MARKER_KEYS = {
    "event_uid", "event_id", "client_event_id", "report_id", "dedup_key",
    "idempotency_key", "session_id", "session_uid", "session",
    "会话编号", "会话ID", "会话标识", "事件唯一编号", "上报编号",
}


@router.post("/access_audit")
async def create_audit_entry_or_event(request: Request) -> Any:
    """兼容脚手架通用登记：识别为事件补送时进会话时间线，否则原样走通用登记。"""
    from fastapi.responses import JSONResponse

    body = await _payload(request)
    raw_values = body.get("values")
    values = raw_values if isinstance(raw_values, dict) else body
    marked = any(key in body or key in values for key in _EVENT_MARKER_KEYS)
    kind = str(body.get("kind") or body.get("type") or values.get("kind") or "")
    if marked or kind in {"late_event", "session_event", "audit_event", "event_report"}:
        payload = _merged_event_payload(body)
        event, created, duplicate, message = svc.report_event(payload)
        if event:
            return _report_response(event, created, duplicate, message)

    service = service_for("access_audit")
    assert service is not None
    entry, missing = service.create_entry(values if isinstance(values, dict) else {})
    if missing:
        result = ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
        return JSONResponse(status_code=200, content=result.model_dump())
    result = ActionResult(ok=True, message=f"{service.ENTITY}已登记", entry=entry)
    return JSONResponse(status_code=200, content=result.model_dump())


@router.post("/access_audit/{entry_ref}/events")
async def report_audit_scoped_event(entry_ref: str, request: Request) -> dict[str, Any]:
    """/api/access_audit/1/events 这类嵌套写法：路径 id 解析不了会话时回落到唯一原会话。"""
    body = await _payload(request)
    payload = _merged_event_payload(body)
    if svc._resolve_session_id(entry_ref) is not None:
        payload.setdefault("session_id", entry_ref)
    event, created, duplicate, message = svc.report_event(payload)
    if not event and svc.sessions:
        payload.pop("session_id", None)
        payload.pop("会话编号", None)
        event, created, duplicate, message = svc.report_event(payload)
    if not event:
        return {"ok": False, "message": message}
    return _report_response(event, created, duplicate, message)


# ================================================================ 场景辅助

LATE_EXPORT_PAYLOAD: dict[str, Any] = {
    "event_uid": "EVT-20261015-1001-EXPORT",
    "事件唯一编号": "EVT-20261015-1001-EXPORT",
    "session_id": 1,
    "会话编号": "SESS-1001",
    "记录编号": "ACCE-1001",
    "event_time": "2026-10-15 10:01",
    "访问时间": "2026-10-15 10:01",
    "operation": "批量导出",
    "访问操作": "批量导出",
    "目标资源": "用户订单明细（2.4万行）",
    "请求IP": "10.0.1.105",
    "访问主体": "数据分析师-张三",
    "访问结果": "成功",
    "敏感等级": "L4",
}


@router.get("/session-review/scenario/late-export-payload")
def late_export_payload() -> dict[str, Any]:
    return {"payload": LATE_EXPORT_PAYLOAD}


@router.post("/session-review/scenario/deliver-late-export")
async def deliver_late_export(request: Request) -> dict[str, Any]:
    """题面场景一键补送：同一载荷可重复调用，第二次起按重复事件去重。"""
    body = await _payload(request)
    payload = dict(LATE_EXPORT_PAYLOAD)
    if isinstance(body.get("overrides"), dict):
        payload.update(body["overrides"])
    event, created, duplicate, message = svc.report_event(payload)
    return _report_response(event, created, duplicate, message)


@router.post("/session-review/reset")
def reset_scenario() -> dict[str, Any]:
    svc.reset()
    return {"ok": True, "message": "会话复核场景已重置为初始状态（仅 10:02 查询，告警待处理）"}
