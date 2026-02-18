<template>
  <div>
    <!-- Back button -->
    <div style="margin-bottom: 20px;">
      <button class="btn btn-secondary" @click="goBack">← 返回邮件列表</button>
    </div>

    <!-- Loading -->
    <div v-if="emailsStore.detailLoading" class="card">
      <div class="loading-center">
        <div class="spinner"></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="emailsStore.error && !email" class="card">
      <div class="card-body" style="text-align: center; color: var(--danger); padding: 40px;">
        ⚠️ {{ emailsStore.error }}
      </div>
    </div>

    <!-- Email Detail -->
    <div v-else-if="email" class="card">
      <div class="email-detail-header">
        <div class="email-detail-subject">{{ email.subject || '(无主题)' }}</div>
        <div class="email-detail-meta">
          <div>
            <strong>发件人:</strong>
            {{ email.sender?.name || '' }}
            &lt;{{ email.sender?.address || '' }}&gt;
          </div>
          <div>
            <strong>收件人:</strong>
            <span v-for="(r, i) in email.to_recipients" :key="i">
              {{ r.name || r.address }}{{ i < email.to_recipients.length - 1 ? ', ' : '' }}
            </span>
          </div>
          <div>
            <strong>时间:</strong>
            {{ formatTime(email.received_at) }}
          </div>
          <div v-if="email.has_attachments" style="color: var(--accent-light);">
            📎 包含附件
          </div>
        </div>
      </div>

      <div class="email-detail-body">
        <iframe
          v-if="email.body_html"
          :srcdoc="bodyWithStyle"
          sandbox="allow-same-origin"
          referrerpolicy="no-referrer"
        ></iframe>
        <div v-else style="color: var(--text-muted); padding: 20px; text-align: center;">
          (无邮件内容)
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useEmailsStore } from '../stores/emails.js'

const route = useRoute()
const router = useRouter()
const emailsStore = useEmailsStore()

const email = computed(() => emailsStore.currentEmail)

const bodyWithStyle = computed(() => {
  if (!email.value?.body_html) return ''
  return `
    <html>
      <head>
        <style>
          body {
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 14px;
            line-height: 1.65;
            color: #333;
            padding: 16px;
            max-width: 100%;
            word-break: break-word;
          }
          img { max-width: 100%; height: auto; }
          a { color: #6366f1; }
          pre { overflow-x: auto; }
        </style>
      </head>
      <body>${email.value.body_html}</body>
    </html>
  `
})

function goBack() {
  router.push('/accounts')
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(() => {
  const { accountId, messageId } = route.params
  if (accountId && messageId) {
    emailsStore.fetchEmailDetail(accountId, messageId)
  }
})

onUnmounted(() => {
  emailsStore.clearDetail()
})
</script>
