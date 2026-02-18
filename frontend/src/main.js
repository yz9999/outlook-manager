import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import axios from 'axios'
import './style.css'

const pinia = createPinia()
const app = createApp(App)

app.use(pinia)
app.use(router)

// Init auth: restore token from localStorage
import { useAuthStore } from './stores/auth.js'
const authStore = useAuthStore()
authStore.init()

// Axios interceptor: redirect to login on 401
axios.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401 && !error.config.url.includes('/api/auth/login')) {
            authStore.logout()
            router.push('/login')
        }
        return Promise.reject(error)
    }
)

app.mount('#app')
