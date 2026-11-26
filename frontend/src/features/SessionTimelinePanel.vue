<template>
  <section class="sessions-panel" data-testid="session-timeline-panel">
    <div class="panel-head">
      <h3>按会话复核 · 服务端操作时间线</h3>
      <button class="btn" type="button" data-testid="reload-sessions" @click="reload">刷新</button>
    </div>
    <p class="panel-tip">
      同一会话内的实际操作由服务端按发生时间排在一起；迟到的导出事件补入原会话并按实际时间归位，
      重复上报同一事件只显示一次。
    </p>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <p v-if="loading && !sessions.length" class="panel-tip">会话加载中…</p>

    <article
      v-for="session in sessions"
      :key="session.session_uid"
      class="session-card"
      :data-testid="`session-card-${session.id}`"
      :data-session-uid="session.session_uid"
    >
      <header class="session-head">
        <div>
          <strong data-testid="session-uid">{{ session.会话编号 ?? session.session_uid }}</strong>
          <span class="session-meta">
            ｜{{ session.访问主体 }} ｜{{ session.请求IP }}
            ｜共 {{ session.event_count }} 条实际操作
          </span>
        </div>
        <div class="session-head-actions">
          <span
            v-if="session.alert"
            class="status-badge small"
            :class="session.alert.pending ? 'pending' : 'confirmed'"
            :data-testid="`session-alert-status-${session.alert.id}`"
          >
            {{ session.alert.current_status }}
          </span>
          <RouterLink
            v-if="session.alert"
            class="btn primary small"
            :to="`/alerts/${session.alert.id}`"
            :data-testid="`alert-detail-link-${session.alert.id}`"
          >
            告警详情
          </RouterLink>
        </div>
      </header>

      <TimelineList :events="session.events ?? []" />

      <AlertReviewCard
        v-if="session.alert"
        :key="`review-${session.alert.id}-${nonce}`"
        class="inline-review"
        :alert-id="session.alert.id"
        :show-current-timeline="false"
        @changed="reload"
      />
    </article>

    <p v-if="!loading && !sessions.length" class="panel-tip">暂无可复核的访问会话。</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listSessions, type SessionItem } from '@/api/session-review'
import AlertReviewCard from './AlertReviewCard.vue'
import TimelineList from './TimelineList.vue'

const sessions = ref<SessionItem[]>([])
const loading = ref(false)
const errorMessage = ref('')
const nonce = ref(0)

async function reload() {
  loading.value = true
  errorMessage.value = ''
  try {
    sessions.value = await listSessions()
    nonce.value += 1
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '会话列表读取失败'
  } finally {
    loading.value = false
  }
}

onMounted(reload)
defineExpose({ reload })
</script>
