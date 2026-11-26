<template>
  <section class="anomaly-alerts" data-testid="anomaly-alert-panel">
    <div class="panel-head">
      <h3>告警复核台（按会话时间线）</h3>
      <button class="btn" type="button" data-testid="reload-alerts" @click="reload">刷新告警</button>
    </div>
    <p class="panel-tip">
      异常检测人员可在此确认或重开告警复核；迟到事件改变告警依据后，这里会显示该告警当前是否仍待处理。
    </p>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <div data-testid="anomaly-alert-list">
      <article
        v-for="alert in alerts"
        :key="alert.id"
        class="alert-row"
        :data-testid="`anomaly-alert-row-${alert.id}`"
        :data-pending="String(alert.pending)"
        :data-basis-changed="String(alert.basis_changed)"
      >
        <div class="alert-row-main">
          <strong>{{ alert.title ?? alert.告警标题 ?? alert.alert_uid }}</strong>
          <span class="alert-row-sub">
            {{ alert.alert_uid }} ｜{{ alert.检测维度 ?? alert.dimension }}
            ｜时间线 {{ alert.timeline?.length ?? 0 }} 条事件
          </span>
        </div>
        <div class="alert-row-side">
          <span
            class="status-badge small"
            :class="alert.pending ? 'pending' : 'confirmed'"
            :data-testid="`anomaly-alert-status-${alert.id}`"
          >
            {{ alert.current_status }}
          </span>
          <span v-if="alert.pending" class="pending-flag" :data-testid="`anomaly-alert-pending-${alert.id}`">
            当前仍待处理
          </span>
          <span v-if="alert.basis_changed" class="basis-flag" :data-testid="`anomaly-basis-changed-${alert.id}`">
            新事件改变告警依据
          </span>
          <RouterLink
            class="btn primary small"
            :to="`/alerts/${alert.id}`"
            :data-testid="`anomaly-alert-detail-${alert.id}`"
          >
            告警详情
          </RouterLink>
          <button
            class="btn small"
            type="button"
            :data-testid="`anomaly-inline-review-${alert.id}`"
            @click="toggleInline(alert.id)"
          >
            {{ inlineId === alert.id ? '收起复核' : '本页复核' }}
          </button>
        </div>
        <AlertReviewCard
          v-if="inlineId === alert.id"
          class="inline-review wide"
          :alert-id="alert.id"
          @changed="reload"
        />
      </article>
      <p v-if="!loading && !alerts.length" class="panel-tip">当前没有告警。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listAlerts, type AlertDetail } from '@/api/session-review'
import AlertReviewCard from './AlertReviewCard.vue'

const route = useRoute()
const alerts = ref<AlertDetail[]>([])
const loading = ref(false)
const errorMessage = ref('')
const inlineId = ref<number | null>(
  route.query.alert ? Number(route.query.alert) : null,
)

function toggleInline(id: number) {
  inlineId.value = inlineId.value === id ? null : id
}

async function reload() {
  loading.value = true
  errorMessage.value = ''
  try {
    alerts.value = await listAlerts()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警列表读取失败'
  } finally {
    loading.value = false
  }
}

onMounted(reload)
defineExpose({ reload })
</script>
