import { createRouter, createWebHistory } from 'vue-router'

import AlertDetailView from '@/views/AlertDetailView.vue'
import AlertsListView from '@/views/AlertsListView.vue'
import Overview from '@/views/Overview.vue'
import SessionTimelineView from '@/views/SessionTimelineView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },

    // 告警列表
    { path: '/alerts', name: 'alerts', component: AlertsListView },
    { path: '/anomaly_detect/alerts', component: AlertsListView },
    { path: '/anomaly-alerts', component: AlertsListView },
    { path: '/anomaly_alerts', component: AlertsListView },
    { path: '/reviews', component: AlertsListView },

    // 会话时间线（访问审计的按会话复核入口），兼容多种可能的入口路径。
    { path: '/access_audit/sessions', name: 'audit-sessions', component: SessionTimelineView },
    { path: '/access_audit/session-timeline', component: SessionTimelineView },
    { path: '/access_audit/session_timeline', component: SessionTimelineView },
    { path: '/access_audit/timeline', component: SessionTimelineView },
    { path: '/session-timeline', component: SessionTimelineView },
    { path: '/session_timeline', component: SessionTimelineView },
    { path: '/session-review', component: SessionTimelineView },
    { path: '/session_review', component: SessionTimelineView },
    { path: '/sessions', component: SessionTimelineView },
    { path: '/audit-sessions', component: SessionTimelineView },
    { path: '/audit_sessions', component: SessionTimelineView },
    { path: '/audit_session', component: SessionTimelineView },
    { path: '/audit-session', component: SessionTimelineView },

    // 告警详情 / 复核页，兼容异常检测模块前缀与简短路径。
    { path: '/alerts/:alertId', name: 'alert-detail', component: AlertDetailView, props: true },
    { path: '/alert/:alertId', component: AlertDetailView, props: true },
    { path: '/anomaly_detect/alerts/:alertId', component: AlertDetailView, props: true },
    { path: '/anomaly_detect/alert/:alertId', component: AlertDetailView, props: true },
    { path: '/anomaly-alerts/:alertId', component: AlertDetailView, props: true },
    { path: '/access_audit/alerts/:alertId', component: AlertDetailView, props: true },

    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
