import { createRouter, createWebHistory } from 'vue-router'
import { sessionToken } from '../features/account/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'presentation',
      component: () => import('../views/LandingView.vue')
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('../views/FoundationView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/AccessView.vue')
    },
    {
      path: '/manage',
      name: 'manage',
      component: () => import('../views/ManageView.vue'),
      meta: { requiresAuth: true }
    }
  ]
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !sessionToken.value) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && sessionToken.value) return { name: 'dashboard' }
})

export default router
