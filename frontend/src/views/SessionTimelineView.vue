<template>
  <section class="page session-timeline-page" data-module="session_timeline" data-testid="session-timeline-page">
    <header class="page-head">
      <div>
        <h2>访问审计 · 会话时间线</h2>
        <p class="page-desc">
          监控人员按会话复核实际操作序列，而不是只看逐条事件；可在时间线上直接确认或重开告警复核。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/access_audit" data-testid="back-to-audit-list">
          返回逐条审计事件
        </RouterLink>
        <RouterLink class="btn ghost" to="/anomaly_detect" data-testid="go-anomaly-page">
          前往异常检测
        </RouterLink>
      </div>
    </header>

    <div class="timeline-page-grid">
      <SessionTimelinePanel ref="panelRef" />
      <EventReportPanel class="timeline-side" @reported="handleReported" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import EventReportPanel from '@/features/EventReportPanel.vue'
import SessionTimelinePanel from '@/features/SessionTimelinePanel.vue'

const panelRef = ref<InstanceType<typeof SessionTimelinePanel> | null>(null)

async function handleReported() {
  await panelRef.value?.reload()
}
</script>
