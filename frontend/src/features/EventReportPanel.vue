<template>
  <section class="report-panel" data-testid="event-report-panel">
    <h4>事件补送 / 重复上报模拟</h4>
    <p class="report-tip">
      导出事件可能迟到。补送时携带同一 <code>event_uid</code> 即视为同一事件，
      服务端幂等去重；事件按实际时间插入原会话，不会生成新的访问会话。
    </p>

    <div class="report-quick">
      <button
        class="btn primary"
        type="button"
        data-testid="deliver-late-export"
        :disabled="busy"
        @click="deliverLate"
      >
        补送 10:01 的导出
      </button>
      <button
        class="btn"
        type="button"
        data-testid="report-duplicate-export"
        :disabled="busy"
        @click="reportDuplicate"
      >
        重复上报同一导出事件
      </button>
    </div>

    <form class="report-form" data-testid="event-report-form" @submit.prevent="submitForm">
      <label>
        <span>事件唯一编号（幂等键）</span>
        <input v-model="form.event_uid" data-testid="report-event-uid" />
      </label>
      <label>
        <span>会话编号</span>
        <input v-model="form.session_uid" data-testid="report-session-uid" />
      </label>
      <label>
        <span>事件时间</span>
        <input v-model="form.event_time" data-testid="report-event-time" placeholder="HH:MM 或 YYYY-MM-DD HH:MM" />
      </label>
      <label>
        <span>访问操作</span>
        <input v-model="form.operation" data-testid="report-event-operation" />
      </label>
      <label class="wide">
        <span>目标资源</span>
        <input v-model="form.target" data-testid="report-event-target" />
      </label>
      <div class="report-submit">
        <button class="btn" type="submit" data-testid="report-event-submit" :disabled="busy">
          {{ busy ? '上报中…' : '上报 / 补送事件' }}
        </button>
      </div>
    </form>

    <p v-if="reportMessage" class="action-message" data-testid="report-result" :data-duplicate="String(lastDuplicate)">
      {{ reportMessage }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'

import { LATE_EXPORT_EVENT, reportEvent } from '@/api/session-review'

const props = defineProps<{ sessionUid?: string | number; alertId?: string | number }>()
const emit = defineEmits<{ reported: [] }>()

const busy = ref(false)
const reportMessage = ref('')
const lastDuplicate = ref(false)

function defaultForm() {
  return {
    event_uid: String(LATE_EXPORT_EVENT.event_uid),
    session_uid: String(props.sessionUid ?? LATE_EXPORT_EVENT.会话编号 ?? 'SESS-1001'),
    event_time: '2026-10-15 10:01',
    operation: '批量导出',
    target: String(LATE_EXPORT_EVENT.目标资源 ?? ''),
  }
}

const form = reactive(defaultForm())

async function send(payload: Record<string, unknown>, okHint?: string) {
  busy.value = true
  reportMessage.value = ''
  try {
    const result = await reportEvent(payload)
    lastDuplicate.value = Boolean(result.duplicate)
    if (!result.ok) throw new Error(result.message || '上报失败')
    reportMessage.value = okHint ? `${okHint}（${result.message}）` : result.message
    emit('reported')
  } catch (error) {
    lastDuplicate.value = false
    reportMessage.value = error instanceof Error ? error.message : '上报失败'
  } finally {
    busy.value = false
  }
}

function deliverLate() {
  return send({ ...LATE_EXPORT_EVENT }, '已补送 10:01 的导出事件')
}

function reportDuplicate() {
  // 与「补送」完全相同的幂等键和业务内容，模拟导出方重复上报。
  return send({ ...LATE_EXPORT_EVENT }, '再次上报同一导出事件')
}

function submitForm() {
  return send({
    event_uid: form.event_uid,
    会话编号: form.session_uid,
    session_id: form.session_uid,
    event_time: form.event_time,
    访问时间: form.event_time,
    operation: form.operation,
    访问操作: form.operation,
    目标资源: form.target,
  })
}

defineExpose({ deliverLate })
</script>
