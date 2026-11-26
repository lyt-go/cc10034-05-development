"""会话时间线与告警复核的领域测试。

每个用例前后都把单例重置回题面初始场景，避免污染同进程的其它测试模块。
HTTP 层用例在缺少 httpx/TestClient 时自动 skip，不影响无该依赖的环境收集。
"""
from __future__ import annotations

import pytest

from app.services.session_review import session_review_service as svc


@pytest.fixture(autouse=True)
def _reset_scenario():
    svc.reset()
    yield
    svc.reset()


class TestSessionTimeline:
    def test_seed_has_single_session_with_1002_query(self):
        sessions = svc.list_sessions()
        assert len(sessions) == 1
        timeline = svc.timeline("SESS-1001")
        assert [e["event_clock"] for e in timeline] == ["10:02"]
        assert timeline[0]["operation_kind"] == "query"

    def test_late_export_joins_original_session(self):
        event, created, duplicate, _ = svc.report_event({
            "event_uid": "E-LATE", "session_id": 1,
            "event_time": "10:01", "operation": "批量导出",
        })
        assert created is True and duplicate is False
        assert event["session_uid"] == "SESS-1001"
        timeline = svc.timeline("SESS-1001")
        assert [e["event_clock"] for e in timeline] == ["10:01", "10:02"]
        assert [e["operation_kind"] for e in timeline] == ["export", "query"]
        # 没有产生新的访问会话
        assert len(svc.list_sessions()) == 1

    def test_duplicate_event_uid_reported_once(self):
        payload = {"event_uid": "E-DUP", "session_id": 1,
                   "event_time": "10:01", "operation": "批量导出"}
        first, created1, dup1, _ = svc.report_event(payload)
        second, created2, dup2, _ = svc.report_event(dict(payload))
        assert created1 and not dup1
        assert not created2 and dup2
        assert first["id"] == second["id"]
        assert len(svc.timeline(1)) == 2  # 10:02 + 唯一一条 10:01

    def test_natural_key_duplicate_without_uid(self):
        base = {"session_id": "SESS-1001", "event_time": "2026-10-15 10:01",
                "operation": "批量导出", "目标资源": "订单明细"}
        svc.report_event(base)
        _, created, duplicate, _ = svc.report_event({
            "session_id": "SESS-1001", "event_time": "10:01",
            "operation": "export", "目标资源": "订单明细",
        })
        assert duplicate is True and created is False

    def test_unknown_session_with_single_seed_falls_back(self):
        event, created, _, _ = svc.report_event({
            "event_uid": "E-X", "event_time": "09:59", "operation": "查询",
        })
        assert created and event["session_id"] == 1


class TestAlertReviewLifecycle:
    def test_initial_alert_pending(self):
        detail = svc.alert_detail(1)
        assert detail["pending"] is True
        assert detail["current_status"] == "待处理"
        assert detail["available_actions"] == ["确认告警"]

    def test_confirm_preserves_snapshot_and_conclusion(self):
        detail, message = svc.confirm_alert(1, "10:02 查询已核对，无异常")
        assert detail is not None and "已确认" in message
        confirm = detail["confirmation"]
        assert confirm["conclusion"] == "10:02 查询已核对，无异常"
        assert [e["event_clock"] for e in confirm["snapshot_events"]] == ["10:02"]
        assert detail["pending"] is False
        assert detail["available_actions"] == ["重开复核"]

    def test_late_event_after_confirm_marks_pending_but_keeps_old_basis(self):
        svc.confirm_alert(1, "当时结论：正常")
        svc.report_event({"event_uid": "E-L", "session_id": 1,
                          "event_time": "10:01", "operation": "批量导出"})
        detail = svc.alert_detail(1)
        # 时间线顺序改变
        assert [e["event_clock"] for e in detail["timeline"]] == ["10:01", "10:02"]
        # 告警当前仍待处理，只能先重开
        assert detail["pending"] is True
        assert detail["basis_changed"] is True
        assert detail["available_actions"] == ["重开复核"]
        # 旧确认依据原样保留
        old = detail["confirmation"]
        assert old["conclusion"] == "当时结论：正常"
        assert [e["event_clock"] for e in old["snapshot_events"]] == ["10:02"]

    def test_reopen_and_reconfirm_keeps_all_reviews(self):
        svc.confirm_alert(1, "第一次结论")
        svc.report_event({"event_uid": "E-L", "session_id": 1,
                          "event_time": "10:01", "operation": "批量导出"})
        detail, _ = svc.reopen_alert(1, "新导出改变依据")
        assert detail["current_status"] == "待复核"
        assert detail["available_actions"] == ["确认告警"]
        detail, _ = svc.confirm_alert(1, "第二次结论：升级处置")
        assert detail["pending"] is False
        assert detail["basis_changed"] is False
        clocks = [e["event_clock"] for e in detail["confirmation"]["snapshot_events"]]
        assert clocks == ["10:01", "10:02"]
        kinds = [r["kind"] for r in detail["reviews"]]
        assert kinds == ["confirm", "reopen", "confirm"]
        conclusions = [r["conclusion"] for r in detail["reviews"] if r["kind"] == "confirm"]
        assert conclusions == ["第一次结论", "第二次结论：升级处置"]

    def test_empty_conclusion_gets_default_and_still_confirms(self):
        detail, _ = svc.confirm_alert(1, "   ")
        assert detail["pending"] is False
        assert detail["confirmation"]["conclusion"]


try:  # HTTP 层可选：没有 httpx 时跳过，避免收集期 ImportError。
    from fastapi.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402
    _client = TestClient(app)
    _HTTP_AVAILABLE = True
except Exception:  # pragma: no cover - 环境相关
    _client = None
    _HTTP_AVAILABLE = False


@pytest.mark.skipif(not _HTTP_AVAILABLE, reason="当前环境没有 httpx/TestClient")
class TestSessionReviewHttp:
    def test_alert_and_alias_endpoints(self):
        assert _client.get("/api/alerts/1").status_code == 200
        assert _client.get("/api/access_audit/sessions").status_code == 200
        assert _client.get("/api/anomaly_detect/alerts").status_code == 200

    def test_full_scenario_over_http(self):
        r = _client.post("/api/anomaly_detect/1/actions",
                         json={"action": "确认告警", "conclusion": "接口确认"})
        assert r.json()["ok"] is True
        r = _client.post("/api/access_audit/events", json={
            "values": {"event_uid": "HTTP-LATE", "会话编号": "SESS-1001",
                       "访问时间": "10:01", "访问操作": "批量导出"}})
        assert r.json()["duplicate"] is False
        r = _client.post("/api/events/report", json={
            "event_uid": "HTTP-LATE", "session_id": 1,
            "event_time": "10:01", "operation": "批量导出"})
        assert r.json()["duplicate"] is True
        detail = _client.get("/api/alerts/1").json()
        assert detail["pending"] is True
        assert detail["available_actions"] == ["重开复核"]

    def test_generic_audit_list_count_unchanged(self):
        body = _client.get("/api/access_audit?size=1").json()
        assert body["total"] == 3
