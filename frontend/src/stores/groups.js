import { defineStore } from 'pinia'
import axios from 'axios'

export const useGroupsStore = defineStore('groups', {
    state: () => ({
        groups: [],
        loading: false,
        error: null,
    }),

    actions: {
        async fetchGroups() {
            this.loading = true
            this.error = null
            try {
                const { data } = await axios.get('/api/groups')
                this.groups = data
            } catch (e) {
                this.error = e.response?.data?.detail || '获取分组失败'
            } finally {
                this.loading = false
            }
        },

        async createGroup(payload) {
            const { data } = await axios.post('/api/groups', payload)
            this.groups.unshift(data)
            return data
        },

        async updateGroup(id, payload) {
            const { data } = await axios.put(`/api/groups/${id}`, payload)
            const idx = this.groups.findIndex((g) => g.id === id)
            if (idx !== -1) this.groups[idx] = data
            return data
        },

        async deleteGroup(id) {
            await axios.delete(`/api/groups/${id}`)
            this.groups = this.groups.filter((g) => g.id !== id)
        },
    },
})
