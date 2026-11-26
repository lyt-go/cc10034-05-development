<template>
  <section v-if="meta" class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button
          v-if="meta.key === 'access_audit'"
          class="btn"
          data-testid="session-timeline-entry"
          type="button"
          @click="scrollToTimeline"
        >
          会话时间线
        </button>
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <AnomalyAlertsPanel v-if="meta.key === 'anomaly_detect'" class="embedded-alerts" />

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <div
      v-if="meta.key === 'access_audit'"
      id="session-timeline-anchor"
      class="timeline-anchor"
      :class="{ highlight: timelineHighlight }"
      data-testid="session-timeline-section"
    >
      <SessionTimelinePanel />
    </div>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>

  <section v-else class="page unknown-module" data-testid="unknown-module">
    <h2>未登记的业务模块：{{ moduleKey }}</h2>
    <p class="page-desc">该路径没有对应工作台，可前往新增的会话复核入口：</p>
    <div class="page-actions">
      <RouterLink class="btn primary" to="/access_audit/sessions">访问审计 · 会话时间线</RouterLink>
      <RouterLink class="btn" to="/alerts">告警复核台</RouterLink>
      <RouterLink class="btn ghost" to="/">返回运营概览</RouterLink>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createEntry,
  downloadEntries,
  listEntries,
  runAction as applyAction,
} from '@/api/backend-service'
import { MODULE_BY_KEY } from '@/data/modules'
import type { EntryRow, ModuleMeta } from '@/data/types'
import AnomalyAlertsPanel from '@/features/AnomalyAlertsPanel.vue'
import SessionTimelinePanel from '@/features/SessionTimelinePanel.vue'

const props = defineProps<{ moduleKey: string }>()
const meta: ModuleMeta | undefined = MODULE_BY_KEY.get(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta ? meta.fields.slice(0, 3) : []
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const timelineHighlight = ref(false)

function scrollToTimeline() {
  const anchor = document.getElementById('session-timeline-anchor')
  anchor?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  timelineHighlight.value = true
  window.setTimeout(() => {
    timelineHighlight.value = false
  }, 1600)
}
const stats = computed(() => {
  if (!meta) return []
  return [
    { label: meta.metrics[0], value: total.value },
    { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
    {
      label: meta.metrics[2],
      value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
    },
  ]
})
const statusSummary = computed(() =>
  (meta?.statuses ?? []).map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  if (!meta) return
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  if (!meta) return
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  if (!meta) return
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  if (!meta) return
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function reload() {
  if (!meta) return
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(reload)
</script>
