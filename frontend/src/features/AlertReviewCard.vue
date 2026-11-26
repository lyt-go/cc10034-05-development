<template>
  <section class="review-card" data-testid="alert-review-card" :data-alert-id="alertId">
    <div v-if="loading && !alert" class="review-loading">告警详情加载中…</div>
    <div v-else-if="!alert" class="review-error" data-testid="alert-not-found">
      告警 {{ alertId }} 不存在或已归档
    </div>

    <template v-else>
      <header class="review-head">
        <div>
          <h3 class="review-title" data-testid="alert-title">
            {{ alert.title ?? alert.告警标题 ?? `告警 ${alert.alert_uid}` }}
          </h3>
          <div class="review-sub">
            <span data-testid="alert-uid">{{ alert.alert_uid ?? alert.告警编号 }}</span>
            <span v-if="alert.检测维度 ?? alert.dimension">
              ｜{{ alert.检测维度 ?? alert.dimension }}
            </span>
            <span v-if="alert.告警级别 ?? alert.level">
              ｜{{ alert.告警级别 ?? alert.level }}
            </span>
          </div>
        </div>
        <span
          class="status-badge"
          :class="alert.pending ? 'pending' : 'confirmed'"
          data-testid="alert-status"
          :data-status="alert.current_status"
          :data-pending="String(alert.pending)"
        >
          {{ alert.current_status }}
        </span>
      </header>

      <div
        v-if="alert.basis_changed"
        class="basis-banner"
        data-testid="basis-changed-banner"
      >
        ⚠ 有迟到事件补入原会话，新事件不在上次确认依据中，告警依据已变化，
        <strong>当前仍待处理</strong>。请先「重开复核」，再按新的时间线重新确认。
      </div>

      <div v-if="showCurrentTimeline" class="review-section">
        <h4>会话时间线（服务端按实际操作时间排列）</h4>
        <TimelineList :events="alert.timeline ?? []" />
      </div>

      <!-- 待处理 / 重开后：填写结论并确认 -->
      <div v-if="canConfirm" class="action-box" data-testid="confirm-box">
        <label class="conclusion-field" :for="`conclusion-${alertId}`">
          <span>复核结论（确认时将留存当时看过的事件）</span>
          <textarea
            :id="`conclusion-${alertId}`"
            v-model="conclusion"
            class="conclusion-input"
            data-testid="confirm-conclusion"
            rows="3"
            placeholder="例如：已核对 10:02 查询及会话上下文，确认告警/说明误报依据…"
          />
        </label>
        <button
          class="btn primary"
          type="button"
          data-testid="confirm-alert"
          :disabled="submitting"
          @click="submitConfirm"
        >
          {{ submitting ? '提交中…' : '确认告警' }}
        </button>
      </div>

      <!-- 已确认且依据变化 / 已确认闭环：可以重开 -->
      <div v-if="canReopen" class="action-box reopen-box" data-testid="reopen-box">
        <p class="reopen-hint">
          {{ alert.basis_changed
            ? '新补送事件改变了告警依据，上次确认仅代表当时的判断。'
            : '如复查发现新的疑点，可以重开本次告警复核。' }}
        </p>
        <button
          class="btn"
          type="button"
          data-testid="reopen-review"
          :disabled="submitting"
          @click="submitReopen"
        >
          {{ submitting ? '提交中…' : '重开复核' }}
        </button>
      </div>

      <p v-if="actionMessage" class="action-message" data-testid="review-action-message">
        {{ actionMessage }}
      </p>
      <p v-if="errorMessage" class="error-text" data-testid="review-error">{{ errorMessage }}</p>

      <!-- 历次确认依据：结论 + 当时快照，永不被新事件覆盖 -->
      <div class="review-section" data-testid="confirmation-records">
        <h4>确认依据留存</h4>
        <article
          v-for="review in confirmReviews"
          :key="review.id"
          class="snapshot-card"
          :data-testid="review.id === alert.confirmation?.id ? 'confirmation-basis' : `confirmation-basis-${review.id}`"
          :data-review-id="review.id"
        >
          <header class="snapshot-head">
            <strong data-testid="confirmation-action">{{ review.action }}</strong>
            <span class="snapshot-meta">
              {{ review.reviewer }} ｜ {{ review.created_at }} ｜ 当时查看
              {{ review.event_count_at_review }} 条事件
            </span>
          </header>
          <p class="conclusion-text" data-testid="confirmation-conclusion">
            复核结论：{{ review.conclusion }}
          </p>
          <TimelineList
            :events="review.snapshot_events ?? []"
            label="确认时看到的事件快照"
            test-id="confirmation-snapshot"
            row-test-id="snapshot-event"
            time-test-id="snapshot-event-time"
          />
        </article>
        <p v-if="!confirmReviews.length" class="no-review">尚未确认过告警，确认后将在此保留当时的事件列表与结论。</p>
      </div>

      <!-- 完整复核轨迹（含重开记录） -->
      <div v-if="alert.reviews?.length" class="review-section" data-testid="review-history">
        <h4>复核轨迹</h4>
        <ol class="history-list">
          <li
            v-for="review in alert.reviews"
            :key="`history-${review.id}`"
            :data-testid="`review-record-${review.id}`"
            :data-kind="review.kind"
          >
            <span class="history-time">{{ review.created_at }}</span>
            <span class="history-action">{{ review.action }}</span>
            <span class="history-by">{{ review.reviewer }}</span>
            <span class="history-conclusion">{{ review.conclusion }}</span>
          </li>
        </ol>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  confirmAlert,
  getAlert,
  reopenAlert,
  type AlertDetail,
} from '@/api/session-review'
import TimelineList from './TimelineList.vue'

const props = withDefaults(defineProps<{
  alertId: string | number
  showCurrentTimeline?: boolean
}>(), {
  showCurrentTimeline: true,
})
const emit = defineEmits<{ changed: [detail: AlertDetail] }>()

const alert = ref<AlertDetail | null>(null)
const loading = ref(false)
const submitting = ref(false)
const conclusion = ref('')
const actionMessage = ref('')
const errorMessage = ref('')

const canConfirm = computed(() => {
  if (!alert.value) return false
  return alert.value.can_confirm === true || (alert.value.pending && !alert.value.basis_changed && alert.value.current_status !== '已确认')
})
const canReopen = computed(() => {
  if (!alert.value) return false
  return alert.value.can_reopen === true || alert.value.current_status === '已确认' || alert.value.basis_changed === true
})

const confirmReviews = computed(() =>
  (alert.value?.reviews ?? []).filter((review) => review.kind === 'confirm'),
)

async function reload() {
  loading.value = true
  errorMessage.value = ''
  try {
    alert.value = await getAlert(props.alertId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警详情读取失败'
  } finally {
    loading.value = false
  }
}

async function submitConfirm() {
  submitting.value = true
  errorMessage.value = ''
  actionMessage.value = ''
  try {
    // 结论可留空，服务端会补默认结论，保证一键确认也留下复核记录。
    const result = await confirmAlert(props.alertId, conclusion.value.trim())
    if (!result.ok) throw new Error(result.message || '确认失败')
    actionMessage.value = result.message
    conclusion.value = ''
    await reload()
    if (alert.value) emit('changed', alert.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '确认失败'
  } finally {
    submitting.value = false
  }
}

async function submitReopen() {
  submitting.value = true
  errorMessage.value = ''
  actionMessage.value = ''
  try {
    const result = await reopenAlert(props.alertId)
    if (!result.ok) throw new Error(result.message || '重开失败')
    actionMessage.value = result.message
    await reload()
    if (alert.value) emit('changed', alert.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重开失败'
  } finally {
    submitting.value = false
  }
}

watch(() => props.alertId, () => void reload())
onMounted(reload)
defineExpose({ reload })
</script>
