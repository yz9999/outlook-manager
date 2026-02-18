import { createRouter, createWebHistory } from 'vue-router'

const routes = [
    {
        path: '/login',
        name: 'Login',
        component: () => import('../views/LoginView.vue'),
        meta: { guest: true },
    },
    {
        path: '/',
        redirect: '/accounts',
    },
    {
        path: '/accounts',
        name: 'Accounts',
        component: () => import('../views/AccountsView.vue'),
    },
    {
        path: '/emails',
        name: 'Emails',
        component: () => import('../views/EmailsView.vue'),
    },
    {
        path: '/emails/:accountId/:messageId',
        name: 'EmailDetail',
        component: () => import('../views/EmailDetailView.vue'),
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// Navigation guard
router.beforeEach((to, from, next) => {
    const token = localStorage.getItem('auth_token')

    if (to.meta.guest) {
        // Login page: if already logged in, redirect to home
        if (token) {
            next('/accounts')
        } else {
            next()
        }
    } else {
        // Protected page: require auth
        if (!token) {
            next('/login')
        } else {
            next()
        }
    }
})

export default router
