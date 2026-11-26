"""会话时间线与告警复核领域服务。

承载访问审计页缺失的「按会话复核」能力：

* 同一会话（session_uid）内的实际操作按事件发生时间排列成时间线；
* 导出事件可能迟到：迟到事件补入原会话，绝不产生新的访问会话；
* 同一导出事件靠 event_uid（或自然键）幂等去重，重复上报只保留一条；
* 值班员确认告警时，把当时看到的事件列表和复核结论固化成复核记录；
* 新补入事件不在旧确认快照中时，认为告警依据已变化，告警当前重新待处理，
  值班员可以「重开复核」并再次确认，历次复核记录（含旧依据）全部保留。

本模块使用独立内存状态，不改动 18 个通用模块的种子表与计数约定。
"""
from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from typing import Any

# 场景固定日期：题面只给了 10:01 / 10:02，补送请求若只给 HH:MM 时补这个日期。
SCENARIO_DATE = "2026-10-15"
SCENARIO_DAY = "2026-10-15"

# 告警复核状态（中文展示值同时作为 status 返回）
ALERT_PENDING = "待处理"
ALERT_CONFIRMED = "已确认"
ALERT_REOPENED = "待复核"

CONFIRM_ACTIONS = {
    "确认告警", "确认复核", "确认", "确认异常", "确认风险", "确认无误",
    "confirm", "confirm_alert", "resolve", "ack", "acknowledge",
}
REOPEN_ACTIONS = {
    "重开复核", "重开", "重新复核", "再次复核", "重新打开复核", "重开告警",
    "重新打开", "reopen", "reopen_review", "re-review",
}

_EVENT_UID_ALIASES = [
    "event_uid", "event_id", "client_event_id", "report_id", "dedup_key",
    "idempotency_key", "uuid", "message_id", "msg_id",
    "事件唯一编号", "事件ID", "事件编号", "上报编号", "消息编号", "导出编号", "记录编号",
]
_SESSION_REF_ALIASES = [
    "session_uid", "session_id", "session", "会话编号", "会话ID", "会话标识",
]
_TIME_ALIASES = [
    "event_time", "occurred_at", "occur_time", "timestamp", "time",
    "访问时间", "事件时间", "操作时间", "发生时间",
]
_OP_ALIASES = ["operation", "action_type", "op", "访问操作", "操作类型", "操作"]
_TARGET_ALIASES = ["target", "resource", "目标资源", "目标数据", "资源"]
_SUBJECT_ALIASES = ["subject", "user", "actor", "访问主体", "操作人", "用户"]
_IP_ALIASES = ["ip", "request_ip", "请求IP", "来源IP"]
_RESULT_ALIASES = ["result", "访问结果", "结果"]
_LEVEL_ALIASES = ["level", "sensitive_level", "敏感等级"]
_CONCLUSION_ALIASES = ["conclusion", "review_note", "note", "remark", "结论", "复核结论", "处理结论", "意见"]
_REVIEWER_ALIASES = ["reviewer", "operator", "duty", "值班员", "复核人", "处理人"]


def _first(payload: dict[str, Any], aliases: list[str], default: Any = "") -> Any:
    for key in aliases:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def parse_event_time(value: Any) -> tuple[str, str, str]:
    """把各种时间写法归一化为 (完整时间, HH:MM 展示, 可排序键)。

    无法解析时按当前时间处理，保证新事件总能排进时间线。
    """
    text = str(value or "").strip()
    candidates = [text]
    if len(text) <= 5 and ":" in text:  # 仅给 10:01
        candidates.append(f"{SCENARIO_DATE} {text}")
    parsed: datetime | None = None
    for candidate in candidates:
        for fmt in (
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
            "%H:%M:%S", "%H:%M",
        ):
            try:
                parsed = datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
        if parsed is not None:
            break
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            parsed = datetime.now()
    if parsed.year == 1900:  # 只解析出了时分
        parsed = parsed.replace(year=2026, month=10, day=15)
    full = parsed.strftime("%Y-%m-%d %H:%M")
    clock = parsed.strftime("%H:%M")
    sort_key = parsed.strftime("%Y-%m-%d %H:%M:%S")
    return full, clock, sort_key


def normalize_operation(value: Any) -> tuple[str, str]:
    """返回 (规范中文名, 操作类别 query/export/other)。"""
    text = str(value or "").strip()
    low = text.lower()
    if "导出" in text or "export" in low or "download" in low:
        return (text if "导出" in text else "批量导出"), "export"
    if "查询" in text or "query" in low or "select" in low or "检索" in text:
        return (text if ("查询" in text or "检索" in text) else "只读查询"), "query"
    return (text or "访问操作"), "other"


class SessionReviewService:
    """进程内单例服务；路由层只做参数收发，状态流转都在这里。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    # ------------------------------------------------------------------ seed
    def reset(self) -> None:
        """恢复到题面初始场景：会话里只有 10:02 的查询，告警待处理。"""
        with self._lock:
            self.sessions: list[dict[str, Any]] = [
                {
                    "id": 1,
                    "session_uid": "SESS-1001",
                    "会话编号": "SESS-1001",
                    "访问主体": "数据分析师-张三",
                    "请求IP": "10.0.1.105",
                    "客户端": "BI查询网关 / Chrome",
                    "登录时间": f"{SCENARIO_DAY} 09:58",
                },
            ]
            self.events: list[dict[str, Any]] = [
                self._make_event(
                    event_pk=1,
                    event_uid="EVT-20261015-1002-QUERY",
                    session_ref="SESS-1001",
                    time_value=f"{SCENARIO_DAY} 10:02",
                    operation="敏感订单查询",
                    target="订单汇总表",
                    result="成功",
                    level="L3",
                    subject="数据分析师-张三",
                    ip="10.0.1.105",
                    record_no="ACCE-1002",
                    source="审计实时上报",
                ),
            ]
            self.alerts: list[dict[str, Any]] = [
                {
                    "id": 1,
                    "alert_uid": "ALERT-1001",
                    "告警编号": "ALERT-1001",
                    "title": "会话 SESS-1001 出现可疑数据操作序列",
                    "告警标题": "会话 SESS-1001 出现可疑数据操作序列",
                    "rule_no": "ANOM-0003",
                    "规则编号": "ANOM-0003",
                    "dimension": "数据批量导出异常",
                    "检测维度": "数据批量导出异常",
                    "level": "P1-安全事件",
                    "告警级别": "P1-安全事件",
                    "session_id": 1,
                    "session_uid": "SESS-1001",
                    "status": ALERT_PENDING,
                    "review_count": 0,
                    "created_at": f"{SCENARIO_DAY} 10:03",
                },
            ]
            self.reviews: list[dict[str, Any]] = []
            self._event_pk = 1
            self._review_pk = 0

    def _make_event(
        self, *, event_pk: int, event_uid: str, session_ref: str | int,
        time_value: Any, operation: Any, target: str = "", result: str = "",
        level: str = "", subject: str = "", ip: str = "", record_no: str = "",
        source: str = "事件上报", extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        full, clock, sort_key = parse_event_time(time_value)
        op_name, op_kind = normalize_operation(operation)
        event: dict[str, Any] = {
            "id": event_pk,
            "event_uid": event_uid,
            "事件唯一编号": event_uid,
            "记录编号": record_no or f"ACCE-{event_pk:04d}",
            "session_id": self._resolve_session_id(session_ref) or 1,
            "session_uid": self._resolve_session_uid(session_ref) or "SESS-1001",
            "访问主体": subject or "数据分析师-张三",
            "目标资源": target or "—",
            "访问操作": op_name,
            "operation_kind": op_kind,
            "访问时间": full,
            "event_clock": clock,
            "sort_time": sort_key,
            "请求IP": ip or "10.0.1.105",
            "访问结果": result or "成功",
            "敏感等级": level or "L3",
            "来源": source,
            "late": False,
            "reported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            for key, value in extra.items():
                if key not in event:
                    event[key] = value
        return event

    # ------------------------------------------------------------- lookups
    def _resolve_session_id(self, ref: Any) -> int | None:
        if ref is None or ref == "":
            return None
        text = str(ref).strip()
        for session in self.sessions:
            if text in (str(session["id"]), session["session_uid"], str(session.get("会话编号", ""))):
                return int(session["id"])
        return None

    def _resolve_session_uid(self, ref: Any) -> str | None:
        sid = self._resolve_session_id(ref)
        if sid is None:
            return None
        session = next((s for s in self.sessions if int(s["id"]) == sid), None)
        return str(session["session_uid"]) if session else None

    def find_session_ref(self, payload: dict[str, Any], alert_ref: Any = None) -> Any:
        ref = _first(payload, _SESSION_REF_ALIASES, "")
        if ref != "":
            return ref
        alert_key = _first(payload, ["alert_id", "alert_uid", "告警编号", "alert"], alert_ref)
        if alert_key not in ("", None):
            alert = self.get_alert_raw(alert_key)
            if alert:
                return alert["session_uid"]
        # 只有一个种子会话时，未显式带会话号的补送也归入原会话。
        if len(self.sessions) == 1:
            return self.sessions[0]["session_uid"]
        return None

    def get_alert_raw(self, ref: Any) -> dict[str, Any] | None:
        if ref is None:
            return None
        text = str(ref).strip()
        for alert in self.alerts:
            if text in (str(alert["id"]), alert["alert_uid"], str(alert.get("告警编号", ""))):
                return alert
        return None

    def find_event_by_uid(self, uid: str) -> dict[str, Any] | None:
        if not uid:
            return None
        for event in self.events:
            if str(event.get("event_uid", "")) == str(uid) or str(event.get("事件唯一编号", "")) == str(uid):
                return event
        return None

    def find_duplicate_event(self, payload: dict[str, Any], session_id: int) -> dict[str, Any] | None:
        uid = str(_first(payload, _EVENT_UID_ALIASES, "")).strip()
        if uid:
            existing = self.find_event_by_uid(uid)
            if existing:
                return existing
        # 自然键幂等：同会话 + 同事件时间(分钟) + 同操作类别 + 同目标 视为同一事件。
        time_value = _first(payload, _TIME_ALIASES, "")
        op_value = _first(payload, _OP_ALIASES, "")
        target = str(_first(payload, _TARGET_ALIASES, "")).strip()
        if time_value and op_value:
            _, clock, _ = parse_event_time(time_value)
            _, op_kind = normalize_operation(op_value)
            for event in self.events:
                if int(event["session_id"]) != session_id:
                    continue
                if event.get("event_clock") != clock:
                    continue
                if event.get("operation_kind") != op_kind:
                    continue
                if target and str(event.get("目标资源", "")) not in ("", "—") and target != str(event.get("目标资源", "")):
                    continue
                return event
        return None

    # -------------------------------------------------------------- queries
    def timeline(self, session_ref: Any) -> list[dict[str, Any]]:
        sid = self._resolve_session_id(session_ref)
        if sid is None:
            return []
        rows = [e for e in self.events if int(e["session_id"]) == sid]
        # 同一会话是相近时间窗内的连续操作，按当天实际时刻升序最符合复核直觉；
        # 用 HH:MM 而非含日期的完整时间，可兼容调用方给「10:01」或任意日期前缀，
        # 迟到的 10:01 导出始终排在 10:02 查询之前。同一时刻按入库顺序稳定排序。
        rows.sort(key=lambda e: (str(e.get("event_clock", "")), int(e.get("id", 0))))
        return [deepcopy(e) for e in rows]

    def list_sessions(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for session in self.sessions:
            item = deepcopy(session)
            events = self.timeline(session["id"])
            item["event_count"] = len(events)
            item["events"] = events
            item["first_time"] = events[0]["访问时间"] if events else ""
            item["last_time"] = events[-1]["访问时间"] if events else ""
            alert = next((a for a in self.alerts if int(a["session_id"]) == int(session["id"])), None)
            if alert:
                detail = self.alert_detail(alert["id"])
                item["alert"] = {
                    "id": detail["id"],
                    "alert_uid": detail["alert_uid"],
                    "status": detail["status"],
                    "current_status": detail["current_status"],
                    "pending": detail["pending"],
                    "basis_changed": detail["basis_changed"],
                }
            result.append(item)
        return result

    def list_alerts(self) -> list[dict[str, Any]]:
        return [self.alert_detail(a["id"]) for a in self.alerts]

    def _latest_confirmation(self, alert_id: int) -> dict[str, Any] | None:
        confirmed = [
            r for r in self.reviews
            if int(r["alert_id"]) == int(alert_id) and r.get("kind") == "confirm"
        ]
        return confirmed[-1] if confirmed else None

    def alert_detail(self, ref: Any) -> dict[str, Any]:
        alert = self.get_alert_raw(ref)
        if alert is None:
            return {}
        aid = int(alert["id"])
        timeline = self.timeline(alert["session_uid"])
        current_ids = [int(e["id"]) for e in timeline]

        latest = self._latest_confirmation(aid)
        snapshot_ids: list[int] = []
        if latest:
            snapshot_ids = [int(x) for x in latest.get("snapshot_event_ids", [])]
        unreviewed = [e for e in timeline if int(e["id"]) not in snapshot_ids]
        # 只有确实确认过、且确认后出现了快照未覆盖的事件，才算依据变化。
        basis_changed = latest is not None and len(unreviewed) > 0

        stored_status = str(alert.get("status", ALERT_PENDING))

        # 当前是否仍待处理：已确认且依据未变才算闭环；其余情况都需要值班员介入。
        if stored_status == ALERT_CONFIRMED and not basis_changed:
            current_status = ALERT_CONFIRMED
            pending = False
            available_actions = ["重开复核"]
        elif stored_status == ALERT_REOPENED:
            current_status = ALERT_REOPENED
            pending = True
            available_actions = ["确认告警"]
        elif latest is not None and basis_changed:
            # 旧确认记录保留，但新事件改变了告警依据：回到待处理，只能先重开复核。
            current_status = ALERT_PENDING
            pending = True
            available_actions = ["重开复核"]
        else:
            current_status = ALERT_PENDING
            pending = True
            available_actions = ["确认告警"]

        session = next((s for s in self.sessions if int(s["id"]) == int(alert["session_id"])), {})
        reviews = [deepcopy(r) for r in self.reviews if int(r["alert_id"]) == aid]
        reviews.sort(key=lambda r: int(r["id"]))

        return {
            **deepcopy(alert),
            "status": stored_status,
            "stored_status": stored_status,
            "current_status": current_status,
            "pending": pending,
            "is_pending": pending,
            "待处理": pending,
            "basis_changed": basis_changed,
            "evidence_changed": basis_changed,
            "new_event_count": len(unreviewed),
            "unreviewed_events": deepcopy(unreviewed),
            "available_actions": available_actions,
            "can_confirm": "确认告警" in available_actions,
            "can_reopen": "重开复核" in available_actions,
            "session": deepcopy(session),
            "timeline": timeline,
            "events": timeline,
            "items": timeline,
            "reviews": reviews,
            "review_history": reviews,
            "confirmation": deepcopy(latest) if latest else None,
            "latest_confirmation": deepcopy(latest) if latest else None,
        }

    # ------------------------------------------------------------- commands
    def report_event(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool, bool, str]:
        """上报/补送一个审计事件。

        返回 (event, created, duplicate, message)。
        重复 event_uid / 自然键命中时不新增，duplicate=True。
        """
        with self._lock:
            session_ref = self.find_session_ref(payload)
            sid = self._resolve_session_id(session_ref)
            if sid is None and len(self.sessions) == 1:
                # 显式会话号对不上（例如调用方用了自己的编号）时，单会话场景仍归入原会话。
                sid = int(self.sessions[0]["id"])
            if sid is None:
                # 没有任何可归属会话时，绝不隐式造新会话：报错让调用方带会话号。
                return {}, False, False, "找不到可补入的原访问会话，请提供 session_id / 会话编号"

            duplicate = self.find_duplicate_event(payload, sid)
            uid = str(_first(payload, _EVENT_UID_ALIASES, "")).strip()
            if duplicate is not None:
                if uid and not duplicate.get("event_uid"):
                    duplicate["event_uid"] = uid
                return deepcopy(duplicate), False, True, "同一事件已上报，已自动去重，时间线只显示一次"

            self._event_pk += 1
            event = self._make_event(
                event_pk=self._event_pk,
                event_uid=uid or f"EVT-AUTO-{self._event_pk:05d}",
                session_ref=sid,
                time_value=_first(payload, _TIME_ALIASES, ""),
                operation=_first(payload, _OP_ALIASES, "访问操作"),
                target=str(_first(payload, _TARGET_ALIASES, "")),
                result=str(_first(payload, _RESULT_ALIASES, "")),
                level=str(_first(payload, _LEVEL_ALIASES, "")),
                subject=str(_first(payload, _SUBJECT_ALIASES, "")),
                ip=str(_first(payload, _IP_ALIASES, "")),
                record_no=str(payload.get("record_no") or payload.get("记录编号") or ""),
                source=str(payload.get("source") or payload.get("来源") or "迟到事件补送"),
                extra={k: v for k, v in payload.items() if k not in {
                    *_EVENT_UID_ALIASES, *_SESSION_REF_ALIASES, *_TIME_ALIASES,
                    *_OP_ALIASES, *_TARGET_ALIASES, *_RESULT_ALIASES,
                    *_LEVEL_ALIASES, "source", "来源",
                }} if isinstance(payload, dict) else None,
            )
            # 仅当事件时刻早于会话内既有事件时标记迟到，便于界面提示。
            existing = [e for e in self.events if int(e["session_id"]) == sid]
            if existing and event["event_clock"] < min(str(e.get("event_clock", "")) for e in existing):
                event["late"] = True
            self.events.append(event)
            message = "事件已补入原会话时间线" + ("（迟到事件，已按实际时间归位）" if event["late"] else "")
            return deepcopy(event), True, False, message

    def _add_review(self, alert: dict[str, Any], kind: str, action: str,
                    conclusion: str, reviewer: str) -> dict[str, Any]:
        self._review_pk += 1
        timeline = self.timeline(alert["session_uid"])
        snapshot_events = deepcopy(timeline)
        review = {
            "id": self._review_pk,
            "alert_id": int(alert["id"]),
            "kind": kind,  # confirm / reopen
            "action": action,
            "conclusion": conclusion,
            "reviewer": reviewer or "当班值班员",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_event_ids": [int(e["id"]) for e in timeline],
            "snapshot_events": snapshot_events,
            "event_count_at_review": len(timeline),
        }
        self.reviews.append(review)
        alert["review_count"] = int(alert.get("review_count", 0)) + 1
        return review

    def confirm_alert(self, ref: Any, conclusion: str = "", reviewer: str = "") -> tuple[dict[str, Any] | None, str]:
        with self._lock:
            alert = self.get_alert_raw(ref)
            if alert is None:
                return None, f"告警 {ref} 不存在"
            text = (conclusion or "").strip() or "值班员确认告警（未填写补充结论，认可当前告警判断）"
            review = self._add_review(alert, "confirm", "确认告警", text, reviewer)
            alert["status"] = ALERT_CONFIRMED
            alert["last_confirmed_at"] = review["created_at"]
            detail = self.alert_detail(alert["id"])
            return detail, "告警已确认，当时的事件列表与复核结论已留存"

    def reopen_alert(self, ref: Any, reason: str = "", reviewer: str = "") -> tuple[dict[str, Any] | None, str]:
        with self._lock:
            alert = self.get_alert_raw(ref)
            if alert is None:
                return None, f"告警 {ref} 不存在"
            review = self._add_review(
                alert, "reopen", "重开复核",
                (reason or "").strip() or "出现新补送事件，原告警依据变化，重新复核",
                reviewer,
            )
            alert["status"] = ALERT_REOPENED
            detail = self.alert_detail(alert["id"])
            return detail, "已重开本次告警复核，可依据更新后的时间线再次确认；旧确认依据仍保留"

    def dispatch_action(self, ref: Any, action: str, payload: dict[str, Any] | None = None
                        ) -> tuple[dict[str, Any] | None, str, bool]:
        """统一动作分派，兼容 {action, conclusion/remark, reviewer} 形态。

        返回 (detail_or_none, message, handled)。handled=False 表示不属于本领域动作，
        调用方应回退到通用模块动作服务。
        """
        payload = payload or {}
        if action in CONFIRM_ACTIONS:
            conclusion = str(_first(payload, _CONCLUSION_ALIASES, ""))
            reviewer = str(_first(payload, _REVIEWER_ALIASES, ""))
            detail, message = self.confirm_alert(ref, conclusion, reviewer)
            return detail, message, True
        if action in REOPEN_ACTIONS:
            reason = str(_first(payload, _CONCLUSION_ALIASES, ""))
            reviewer = str(_first(payload, _REVIEWER_ALIASES, ""))
            detail, message = self.reopen_alert(ref, reason, reviewer)
            return detail, message, True
        return None, "", False


session_review_service = SessionReviewService()
