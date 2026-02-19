import { defineStore } from 'pinia'
import axios from 'axios'

export const useAccountsStore = defineStore('accounts', {
    state: () => ({
        accounts: [],
        loading: false,
        error: null,
    }),

    getters: {
        totalUnread: (state) =>
            state.accounts.reduce((sum, a) => sum + (a.unread_count || 0), 0),
    },

    actions: {
        async fetchAccounts(groupId) {
            this.loading = true
            this.error = null
            try {
                const params = {}
                if (groupId != null) params.group_id = groupId
                const { data } = await axios.get('/api/accounts', { params })
                this.accounts = data
            } catch (e) {
                this.error = e.response?.data?.detail || '获取账号失败'
            } finally {
                this.loading = false
            }
        },

        async addAccount(payload) {
            const { data } = await axios.post('/api/accounts', payload)
            this.accounts.unshift(data)
            return data
        },

        async batchImport(text, groupId) {
            const body = { text }
            if (groupId != null) body.group_id = groupId
            const { data } = await axios.post('/api/accounts/batch', body)
            await this.fetchAccounts()
            return data
        },

        async deleteAccount(id) {
            await axios.delete(`/api/accounts/${id}`)
            this.accounts = this.accounts.filter((a) => a.id !== id)
        },

        async updateAccountGroup(id, groupId) {
            await axios.patch(`/api/accounts/${id}/group`, { group_id: groupId })
            const account = this.accounts.find((a) => a.id === id)
            if (account) account.group_id = groupId
        },

        async syncAccount(id) {
            const account = this.accounts.find((a) => a.id === id)
            if (account) account.status = 'syncing'
            try {
                const { data } = await axios.post(`/api/accounts/${id}/sync`)
                if (account) {
                    account.status = 'active'
                    account.unread_count = data.unread_count
                    account.last_synced = new Date().toISOString()
                    account.last_error = null
                    if (data.imap_enabled !== undefined) account.imap_enabled = data.imap_enabled
                    if (data.pop3_enabled !== undefined) account.pop3_enabled = data.pop3_enabled
                    if (data.graph_enabled !== undefined) account.graph_enabled = data.graph_enabled
                }
                return data
            } catch (e) {
                if (account) {
                    account.status = 'error'
                    account.last_error = e.response?.data?.detail || '同步失败'
                }
                throw e
            }
        },
    },
})
