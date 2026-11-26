/** 会话时间线与告警复核接口封装。 */
import { request } from './client'

export type TimelineEvent = {
  id: number
  event_uid: string
  记录编号?: string
  session_id: number
  session_uid: string
  访问主体?: string
  目标资源?: string
  访问操作?: string
  operation_kind?: string
  访问时间: string
  event_clock: string
  sort_time: string
  请求IP?: string
  访问结果?: string
  敏感等级?: string
  late?: boolean
  [key: string]: unknown
}

export type ReviewRecord = {
  id: number
  alert_id: number
  kind: 'confirm' | 'reopen'
  action: string
  conclusion: string
  reviewer: string
  created_at: string
  snapshot_event_ids: number[]
  snapshot_events: TimelineEvent[]
  event_count_at_review: number
}

export type AlertDetail = {
  id: number
  alert_uid: string
  告警编号?: string
  title?: string
  告警标题?: string
  status: string
  current_status: string
  pending: boolean
  basis_changed: boolean
  new_event_count?: number
  available_actions: string[]
  can_confirm: boolean
  can_reopen: boolean
  timeline: TimelineEvent[]
  events?: TimelineEvent[]
  reviews: ReviewRecord[]
  confirmation: ReviewRecord | null
  session?: Record<string, unknown>
  [key: string]: unknown
}

export type SessionItem = {
  id: number
  session_uid: string
  会话编号?: string
  访问主体?: string
  请求IP?: string
  event_count: number
  events: TimelineEvent[]
  alert?: {
    id: number
    status: string
    current_status: string
    pending: boolean
    basis_changed: boolean
  }
  [key: string]: unknown
}

async function readJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) throw new Error(fallbackMessage)
  return (await response.json()) as T
}

export async function listSessions(): Promise<SessionItem[]> {
  const response = await request('/api/access_audit/sessions')
  const data = await readJson<{ items?: SessionItem[] } | SessionItem[]>(response, '会话列表读取失败')
  return Array.isArray(data) ? data : data.items ?? []
}

export async function listAlerts(): Promise<AlertDetail[]> {
  const response = await request('/api/anomaly_detect/alerts')
  const data = await readJson<{ items?: AlertDetail[] } | AlertDetail[]>(response, '告警列表读取失败')
  return Array.isArray(data) ? data : data.items ?? []
}

export async function getAlert(alertId: string | number): Promise<AlertDetail> {
  const response = await request(`/api/anomaly_detect/alerts/${alertId}`)
  return readJson<AlertDetail>(response, '告警详情读取失败')
}

export async function confirmAlert(
  alertId: string | number,
  conclusion: string,
  reviewer = '当班值班员',
): Promise<{ ok: boolean; message: string; entry?: AlertDetail } & Record<string, unknown>> {
  const response = await request(`/api/alerts/${alertId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ conclusion, reviewer }),
  })
  return response.json()
}

export async function reopenAlert(
  alertId: string | number,
  reason = '',
  reviewer = '当班值班员',
): Promise<{ ok: boolean; message: string; entry?: AlertDetail } & Record<string, unknown>> {
  const response = await request(`/api/alerts/${alertId}/reopen`, {
    method: 'POST',
    body: JSON.stringify({ conclusion: reason, reviewer }),
  })
  return response.json()
}

export async function reportEvent(
  payload: Record<string, unknown>,
): Promise<{ ok: boolean; message: string; duplicate?: boolean; created?: boolean }> {
  const response = await request('/api/access_audit/events', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json()
}

/** 题面场景的 10:01 迟到导出事件（固定幂等键，重复上报只显示一次）。 */
export const LATE_EXPORT_EVENT: Record<string, unknown> = {
  event_uid: 'EVT-20261015-1001-EXPORT',
  session_id: 1,
  会话编号: 'SESS-1001',
  记录编号: 'ACCE-1001',
  event_time: '2026-10-15 10:01',
  访问时间: '2026-10-15 10:01',
  operation: '批量导出',
  访问操作: '批量导出',
  目标资源: '用户订单明细（2.4万行）',
  请求IP: '10.0.1.105',
  访问主体: '数据分析师-张三',
  访问结果: '成功',
  敏感等级: 'L4',
}
