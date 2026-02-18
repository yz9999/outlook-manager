import { defineStore } from 'pinia'
import axios from 'axios'

export const useAuthStore = defineStore('auth', {
    state: () => ({
        token: localStorage.getItem('auth_token') || null,
        username: localStorage.getItem('auth_username') || null,
    }),

    getters: {
        isLoggedIn: (state) => !!state.token,
    },

    actions: {
        async login(username, password) {
            const { data } = await axios.post('/api/auth/login', { username, password })
            this.token = data.token
            this.username = data.username
            localStorage.setItem('auth_token', data.token)
            localStorage.setItem('auth_username', data.username)
            // Set default header for future requests
            axios.defaults.headers.common['Authorization'] = `Bearer ${data.token}`
        },

        logout() {
            this.token = null
            this.username = null
            localStorage.removeItem('auth_token')
            localStorage.removeItem('auth_username')
            delete axios.defaults.headers.common['Authorization']
        },

        // Call on app init to restore token
        init() {
            if (this.token) {
                axios.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
            }
        },
    },
})
