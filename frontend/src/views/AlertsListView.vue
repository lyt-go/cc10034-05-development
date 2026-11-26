<template>
  <section class="page alerts-list-page" data-testid="alerts-list-page">
    <header class="page-head">
      <div>
        <h2>异常告警复核</h2>
        <p class="page-desc">按会话时间线确认或重开告警复核；依据变化的告警会显示当前仍待处理。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/anomaly_detect">前往异常检测模块</RouterLink>
      </div>
    </header>
    <AnomalyAlertsPanel />
  </section>
</template>

<script setup lang="ts">
import AnomalyAlertsPanel from '@/features/AnomalyAlertsPanel.vue'
</script>
