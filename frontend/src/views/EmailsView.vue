<template>
  <div>
    <h1 style="font-size: 1.5rem; font-weight: 700; margin-bottom: 20px;">📬 邮件查看</h1>

    <!-- Step 1: Group Selector -->
    <div style="margin-bottom: 12px;">
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px; font-weight: 500;">
        1️⃣ 选择分组
      </div>
      <div class="account-selector">
        <div
          class="account-chip"
          :class="{ active: selectedGroupId === null }"
          @click="selectGroup(null)"
        >全部</div>
        <div
          class="account-chip"
          :class="{ active: selectedGroupId === 0 }"
          @click="selectGroup(0)"
        >未分组</div>
        <div
          v-for="group in groups"
          :key="group.id"
          class="account-chip"
          :class="{ active: selectedGroupId === group.id }"
          @click="selectGroup(group.id)"
        >
          {{ group.name }}
          <span class="chip-unread" v-if="group.account_count > 0">{{ group.account_count }}</span>
        </div>
      </div>
    </div>

    <!-- Step 2: Account Selector (within selected group) -->
    <div style="margin-bottom: 20px;">
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px; font-weight: 500;">
        2️⃣ 选择邮箱
      </div>
      <div class="account-selector">
        <div
          v-for="account in groupAccounts"
          :key="account.id"
          class="account-chip"
          :class="{ active: selectedAccountId === account.id }"
          @click="selectAccount(account.id)"
        >
          <span>{{ account.email.split('@')[0] }}</span>
          <span v-if="account.unread_count > 0" class="chip-unread">{{ account.unread_count }}</span>
        </div>
        <div v-if="groupAccounts.length === 0" style="color: var(--text-muted); font-size: 0.85rem; padding: 8px 16px;">
          {{ accounts.length === 0 ? '请先添加账号' : '该分组暂无账号' }}
        </div>
      </div>
    </div>

    <!-- No accounts -->
    <div v-if="accounts.length === 0" class="card">
      <div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div class="empty-state-text">请先添加账号</div>
        <div class="empty-state-hint">
          <router-link to="/accounts" class="btn btn-primary" style="margin-top: 12px;">前往添加</router-link>
        </div>
      </div>
    </div>

    <!-- Email List -->
    <div v-else-if="selectedAccountId" class="card">
      <div class="card-header">
        <h2>
          收件箱
          <span v-if="emailsStore.total > 0" style="color: var(--text-muted); font-weight: 400; font-size: 0.85rem;">
            ({{ emailsStore.total }})
          </span>
        </h2>
        <button class="btn btn-secondary btn-sm" @click="refreshEmails" :disabled="emailsStore.loading">
          🔄 刷新
        </button>
      </div>

      <div v-if="emailsStore.loading" class="loading-center">
        <div class="spinner"></div>
      </div>

      <div v-else-if="emailsStore.error" class="card-body">
        <div style="color: var(--danger); text-align: center; padding: 20px;">
          ⚠️ {{ emailsStore.error }}
        </div>
      </div>

      <div v-else-if="emails.length === 0" class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div class="empty-state-text">收件箱为空</div>
      </div>

      <div v-else class="email-list">
        <div
          v-for="email in emails"
          :key="email.id"
          class="email-item"
          :class="{ unread: !email.is_read }"
          @click="openEmail(email)"
        >
          <div class="email-dot"></div>
          <div class="email-body">
            <div class="email-sender">
              {{ email.sender?.name || email.sender?.address || '未知发件人' }}
            </div>
            <div class="email-subject">{{ email.subject || '(无主题)' }}</div>
            <div class="email-preview">{{ email.preview }}</div>
          </div>
          <div class="email-time">{{ formatTime(email.received_at) }}</div>
        </div>
      </div>
    </div>

    <!-- Prompt to select -->
    <div v-else class="card">
      <div class="empty-state">
        <div class="empty-state-icon">👆</div>
        <div class="empty-state-text">请先选择分组，再选择邮箱查看邮件</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAccountsStore } from '../stores/accounts.js'
import { useGroupsStore } from '../stores/groups.js'
import { useEmailsStore } from '../stores/emails.js'

const router = useRouter()
const route = useRoute()
const accountsStore = useAccountsStore()
const groupsStore = useGroupsStore()
const emailsStore = useEmailsStore()

const accounts = computed(() => accountsStore.accounts)
const groups = computed(() => groupsStore.groups)
const emails = computed(() => emailsStore.emails)

const selectedGroupId = ref(null)
const selectedAccountId = ref(null)

// Accounts filtered by selected group
const groupAccounts = computed(() => {
  if (selectedGroupId.value === null) return accounts.value
  if (selectedGroupId.value === 0) return accounts.value.filter(a => !a.group_id)
  return accounts.value.filter(a => a.group_id === selectedGroupId.value)
})

function selectGroup(gid) {
  selectedGroupId.value = gid
  selectedAccountId.value = null
  emailsStore.emails = []
  emailsStore.total = 0
}

function selectAccount(id) {
  selectedAccountId.value = id
  emailsStore.fetchEmails(id)
}

function refreshEmails() {
  if (selectedAccountId.value) {
    emailsStore.fetchEmails(selectedAccountId.value)
  }
}

function openEmail(email) {
  router.push(`/emails/${selectedAccountId.value}/${email.id}`)
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  if (d.toDateString() === now.toDateString()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Auto-select account if navigated with ?account=ID
function autoSelectFromQuery() {
  const qid = parseInt(route.query.account)
  if (!qid || accounts.value.length === 0) return

  const account = accounts.value.find(a => a.id === qid)
  if (account) {
    // Set group to match the account's group
    selectedGroupId.value = account.group_id || null
    selectAccount(qid)
  }
}

watch(accounts, () => {
  if (route.query.account && !selectedAccountId.value) {
    autoSelectFromQuery()
  }
})

onMounted(() => {
  groupsStore.fetchGroups()
  accountsStore.fetchAccounts()
})
</script>

