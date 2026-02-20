import { defineStore } from 'pinia'
import axios from 'axios'

export const useEmailsStore = defineStore('emails', {
    state: () => ({
        emails: [],
        total: 0,
        method: null,  // "Graph API" / "IMAP (New)" / "IMAP (Old)" / "Local DB"
        currentEmail: null,
        loading: false,
        detailLoading: false,
        selectedAccountId: null,
        currentFolder: 'inbox',
        error: null,
    }),

    actions: {
        async fetchEmails(accountId, top = 30, skip = 0, folder = 'inbox') {
            this.loading = true
            this.error = null
            this.selectedAccountId = accountId
            this.currentFolder = folder
            try {
                const { data } = await axios.get(
                    `/api/accounts/${accountId}/emails`,
                    { params: { top, skip, folder } }
                )
                this.emails = data.emails
                this.total = data.total
                this.method = data.method || null
            } catch (e) {
                const detail = e.response?.data?.detail
                if (typeof detail === 'object' && detail.errors) {
                    this.error = detail
                } else {
                    this.error = detail || '获取邮件失败'
                }
                this.emails = []
            } finally {
                this.loading = false
            }
        },

        async fetchEmailDetail(accountId, messageId) {
            this.detailLoading = true
            try {
                const { data } = await axios.get(
                    `/api/accounts/${accountId}/emails/${messageId}`
                )
                this.currentEmail = data
            } catch (e) {
                this.error = e.response?.data?.detail || '获取邮件详情失败'
            } finally {
                this.detailLoading = false
            }
        },

        async deleteEmail(accountId, messageId) {
            await axios.delete(`/api/accounts/${accountId}/emails/${messageId}`)
        },

        async batchDeleteEmails(accountId, messageIds) {
            const { data } = await axios.post(
                `/api/accounts/${accountId}/emails/batch-delete`,
                { message_ids: messageIds }
            )
            return data
        },

        clearDetail() {
            this.currentEmail = null
        },
    },
})
