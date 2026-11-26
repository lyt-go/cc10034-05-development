"""业务路由汇总：固定/联动路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import cross_links, resource, session_review

ROUTERS = [session_review, cross_links, resource]
