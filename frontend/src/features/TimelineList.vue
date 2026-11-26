<template>
  <ol
    class="event-timeline"
    :data-testid="testId"
    :aria-label="label"
  >
    <li
      v-for="(event, index) in events"
      :key="String(event.event_uid ?? event.id)"
      class="event-item"
      :class="[`op-${event.operation_kind ?? 'other'}`, { late: event.late }]"
      :data-testid="rowTestId"
      :data-uid="String(event.event_uid ?? event.id)"
      :data-event-id="String(event.id)"
      :data-time="event.event_clock"
      :data-order="index"
    >
      <div class="event-time">
        <span class="clock" :data-testid="timeTestId">{{ event.event_clock }}</span>
        <span v-if="event.late" class="late-tag" data-testid="late-tag">迟到补送</span>
      </div>
      <div class="event-body">
        <div class="event-title">
          <span class="event-op">{{ event.访问操作 }}</span>
          <span class="event-target">{{ event.目标资源 }}</span>
        </div>
        <div class="event-meta">
          <span>{{ event.访问主体 }}</span>
          <span>{{ event.请求IP }}</span>
          <span>结果：{{ event.访问结果 }}</span>
          <span>敏感等级：{{ event.敏感等级 }}</span>
          <span v-if="event.记录编号">编号：{{ event.记录编号 }}</span>
        </div>
      </div>
    </li>
    <li v-if="!events.length" class="timeline-empty">该会话暂无操作事件</li>
  </ol>
</template>

<script setup lang="ts">
import type { TimelineEvent } from '@/api/session-review'

withDefaults(defineProps<{
  events: TimelineEvent[]
  label?: string
  testId?: string
  rowTestId?: string
  timeTestId?: string
}>(), {
  label: '会话操作时间线',
  testId: 'session-timeline',
  rowTestId: 'timeline-event',
  timeTestId: 'timeline-event-time',
})
</script>
