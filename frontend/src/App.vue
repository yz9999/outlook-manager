<template>
  <div class="app-layout">
    <header class="topbar">
      <div class="topbar-brand">
        <div class="topbar-brand-icon">📮</div>
        <span>Outlook 邮箱管理</span>
      </div>

      <div class="topbar-actions">
        <span v-if="syncStatus" class="sync-status-hint">
          <template v-if="syncStatus.in_cooldown">
            ⏸ 冷却中，第{{ syncStatus.current_round }}轮待开始
          </template>
          <template v-else>
            ⏱ 第{{ syncStatus.current_round }}轮 · 每{{ syncStatus.interval_minutes }}分钟/个
          </template>
        </span>

        <button
          class="btn btn-secondary btn-sm"
          @click="toggleAutoRefresh"
          :title="notifStore.autoRefresh ? '关闭自动刷新' : '开启自动刷新'"
        >
          {{ notifStore.autoRefresh ? '🔄 自动刷新 ON' : '⏸ 自动刷新 OFF' }}
        </button>

        <button
          class="btn btn-secondary btn-sm"
          @click="showSyncLog = !showSyncLog"
          title="同步日志"
        >
          📋 日志
        </button>

        <div class="notif-badge" v-if="accountsStore.totalUnread > 0">
          <span>📬</span>
          <span class="notif-count">{{ accountsStore.totalUnread }}</span>
        </div>
      </div>
    </header>

    <main class="main-content">
      <router-view />
    </main>

    <!-- Sync Log Panel -->
    <Transition name="slide-panel">
      <div v-if="showSyncLog" class="sync-log-overlay" @click.self="showSyncLog = false">
        <div class="sync-log-panel">
          <div class="sync-log-header">
            <h3>📋 同步日志</h3>
            <div style="display:flex;gap:8px;align-items:center">
              <button class="btn btn-secondary btn-sm" @click="fetchSyncLog">🔄 刷新</button>
              <button class="btn btn-icon btn-secondary" @click="showSyncLog = false">✕</button>
            </div>
          </div>
          <div class="sync-log-body">
            <div v-if="syncLogLoading" class="loading-center"><div class="spinner"></div></div>
            <div v-else-if="syncLogEntries.length === 0" class="empty-state" style="padding:30px">
              <div style="font-size:2rem;margin-bottom:8px">📭</div>
              <div>暂无同步日志</div>
            </div>
            <div v-else class="sync-log-list">
              <div
                v-for="(entry, i) in syncLogEntries"
                :key="i"
                class="sync-log-entry"
                :class="'sync-log-' + entry.level"
              >
                <span class="sync-log-time">{{ formatLogTime(entry.time) }}</span>
                <span class="sync-log-level-dot"></span>
                <span v-if="entry.email !== '-'" class="sync-log-email">{{ entry.email }}</span>
                <span class="sync-log-msg">{{ entry.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Toast container -->
    <div class="toast-container">
      <div
        v-for="toast in notifStore.toasts"
        :key="toast.id"
        class="toast"
        :class="'toast-' + toast.type"
      >
        {{ toast.message }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { useAccountsStore } from './stores/accounts.js'
import { useGroupsStore } from './stores/groups.js'
import { useNotificationStore } from './stores/notification.js'

const accountsStore = useAccountsStore()
const groupsStore = useGroupsStore()
const notifStore = useNotificationStore()
const syncStatus = ref(null)
const showSyncLog = ref(false)
const syncLogEntries = ref([])
const syncLogLoading = ref(false)

async function fetchSyncStatus() {
  try {
    const { data } = await axios.get('/api/sync-status')
    syncStatus.value = data
  } catch {
    // silent
  }
}

async function fetchSyncLog() {
  syncLogLoading.value = true
  try {
    const { data } = await axios.get('/api/sync-log')
    syncLogEntries.value = data
  } catch {
    // silent
  } finally {
    syncLogLoading.value = false
  }
}

function formatLogTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function toggleAutoRefresh() {
  notifStore.autoRefresh = !notifStore.autoRefresh
  if (notifStore.autoRefresh) {
    accountsStore.fetchAccounts()
    notifStore.checkNotifications()
    notifStore.startPolling(60000, () => accountsStore.fetchAccounts())
  } else {
    notifStore.stopPolling()
  }
}

// Auto-refresh log when panel is opened
import { watch } from 'vue'
watch(showSyncLog, (v) => {
  if (v) fetchSyncLog()
})

onMounted(() => {
  accountsStore.fetchAccounts()
  groupsStore.fetchGroups()
  fetchSyncStatus()
})

onUnmounted(() => {
  notifStore.stopPolling()
})
</script>
