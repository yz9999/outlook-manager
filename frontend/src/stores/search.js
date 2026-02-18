import { defineStore } from 'pinia'
import axios from 'axios'

export const useSearchStore = defineStore('search', {
    state: () => ({
        keyword: '',
        groupId: null,
        results: [],
        total: 0,
        page: 1,
        pageSize: 50,
        loading: false,
        error: null,
        searched: false,
    }),

    actions: {
        async search(keyword, groupId, page = 1) {
            this.keyword = keyword
            this.groupId = groupId
            this.page = page
            this.loading = true
            this.error = null
            this.searched = true
            try {
                const params = { keyword, page, page_size: this.pageSize }
                if (groupId != null) params.group_id = groupId
                const { data } = await axios.get('/api/emails/search', { params })
                this.results = data.results
                this.total = data.total
            } catch (e) {
                this.error = e.response?.data?.detail || '搜索失败'
                this.results = []
                this.total = 0
            } finally {
                this.loading = false
            }
        },

        clearSearch() {
            this.keyword = ''
            this.groupId = null
            this.results = []
            this.total = 0
            this.page = 1
            this.searched = false
            this.error = null
        },
    },
})
