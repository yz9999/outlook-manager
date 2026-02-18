<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-icon">📮</div>
      <h1 class="login-title">Outlook 邮箱管理</h1>
      <p class="login-subtitle">请输入账号密码登录</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label class="form-label">用户名</label>
          <input
            class="form-input"
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            autofocus
          />
        </div>

        <div class="form-group">
          <label class="form-label">密码</label>
          <input
            class="form-input"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </div>

        <div v-if="error" class="login-error">{{ error }}</div>

        <button class="btn btn-primary login-btn" :disabled="loading" type="submit">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await authStore.login(username.value, password.value)
    router.push('/accounts')
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  backdrop-filter: blur(16px);
  padding: 48px 36px;
  text-align: center;
  box-shadow: var(--shadow-lg);
}

.login-icon {
  font-size: 3rem;
  margin-bottom: 12px;
}

.login-title {
  font-size: 1.5rem;
  font-weight: 700;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 6px;
}

.login-subtitle {
  color: var(--text-muted);
  font-size: 0.9rem;
  margin-bottom: 32px;
}

.login-form {
  text-align: left;
}

.login-form .form-group {
  margin-bottom: 20px;
}

.login-form .form-input {
  padding: 12px 16px;
  font-size: 0.95rem;
}

.login-error {
  color: var(--danger);
  font-size: 0.85rem;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: var(--radius-md);
}

.login-btn {
  width: 100%;
  padding: 12px;
  font-size: 1rem;
  font-weight: 600;
  justify-content: center;
  margin-top: 8px;
}
</style>
