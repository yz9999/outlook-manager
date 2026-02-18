import { defineStore } from 'pinia'
import axios from 'axios'

export const useNotificationStore = defineStore('notification', {
    state: () => ({
        newEmails: {},       // { accountId: count }
        totalNew: 0,
        autoRefresh: false,
        intervalId: null,
        toasts: [],
    }),

    actions: {
        async checkNotifications() {
            try {
                const { data } = await axios.get('/api/notifications')
                this.newEmails = data.new_emails || {}
                this.totalNew = Object.values(this.newEmails).reduce(
                    (s, c) => s + c, 0
                )
                if (this.totalNew > 0) {
                    this.addToast(`📬 ${this.totalNew} 封新邮件`, 'info')
                }
            } catch {
                // silent
            }
        },

        startPolling(intervalMs = 60000, onTick = null) {
            this.stopPolling()
            this.intervalId = setInterval(() => {
                if (this.autoRefresh) {
                    this.checkNotifications()
                    if (onTick) onTick()
                }
            }, intervalMs)
        },

        stopPolling() {
            if (this.intervalId) {
                clearInterval(this.intervalId)
                this.intervalId = null
            }
        },

        addToast(message, type = 'info') {
            const id = Date.now()
            this.toasts.push({ id, message, type })
            setTimeout(() => {
                this.toasts = this.toasts.filter((t) => t.id !== id)
            }, 4000)
        },
    },
})
