<template>
  <section class="page alert-detail-page" data-module="alert_detail" data-testid="alert-detail-page">
    <header class="page-head">
      <div>
        <h2>告警详情 · 会话复核</h2>
        <p class="page-desc">
          服务端把同一会话内的实际操作按时间排在一起；确认时留存当时的事件与结论，
          迟到事件补入后可在此核对时间线顺序、旧确认依据，并决定是否重开复核。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/anomaly_detect" data-testid="back-to-anomaly">
          返回异常检测
        </RouterLink>
        <RouterLink class="btn ghost" to="/access_audit/sessions" data-testid="back-to-sessions">
          访问审计 · 按会话复核
        </RouterLink>
      </div>
    </header>

    <div class="detail-grid">
      <AlertReviewCard ref="reviewCardRef" :alert-id="alertId" class="detail-main" />
      <aside class="detail-side">
        <EventReportPanel :alert-id="alertId" @reported="handleReported" />
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import AlertReviewCard from '@/features/AlertReviewCard.vue'
import EventReportPanel from '@/features/EventReportPanel.vue'

const props = defineProps<{ alertId?: string }>()
const alertId = ref<string>(props.alertId ?? '1')
const reviewCardRef = ref<InstanceType<typeof AlertReviewCard> | null>(null)

async function handleReported() {
  // 补送/重复上报后，重新拉取告警详情与时间线。
  await reviewCardRef.value?.reload()
}
</script>
