import { defineStore } from 'pinia'
import axios from 'axios'

export const useEmailsStore = defineStore('emails', {
    state: () => ({
        emails: [],
        total: 0,
        currentEmail: null,
        loading: false,
        detailLoading: false,
        selectedAccountId: null,
        error: null,
    }),

    actions: {
        async fetchEmails(accountId, top = 30, skip = 0) {
            this.loading = true
            this.error = null
            this.selectedAccountId = accountId
            try {
                const { data } = await axios.get(
                    `/api/accounts/${accountId}/emails`,
                    { params: { top, skip } }
                )
                this.emails = data.emails
                this.total = data.total
            } catch (e) {
                this.error = e.response?.data?.detail || '获取邮件失败'
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

        clearDetail() {
            this.currentEmail = null
        },
    },
})
