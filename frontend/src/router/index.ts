import { createRouter, createWebHistory } from 'vue-router'
import { nextTick } from 'vue'
import { sessionToken } from '../features/account/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'presentation',
      meta: { title: 'ColdSafe' },
      component: () => import('../views/LandingView.vue')
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('../views/FoundationView.vue'),
      meta: { requiresAuth: true, title: 'Monitoramento · ColdSafe' }
    },
    {
      path: '/laboratory',
      name: 'laboratory',
      component: () => import('../views/LaboratoryView.vue'),
      meta: { requiresAuth: true, title: 'Laboratório de Dados · ColdSafe' }
    },
    {
      path: '/messaging',
      name: 'messaging',
      component: () => import('../views/MessagingView.vue'),
      meta: { requiresAuth: true, title: 'Mensageria · ColdSafe' }
    },
    {
      path: '/login',
      name: 'login',
      meta: { title: 'Entrar · ColdSafe' },
      component: () => import('../views/AccessView.vue')
    },
    {
      path: '/manage',
      name: 'manage',
      component: () => import('../views/ManageView.vue'),
      meta: { requiresAuth: true, title: 'Ambientes e dispositivos · ColdSafe' }
    }
  ]
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !sessionToken.value) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && sessionToken.value) return { name: 'dashboard' }
})

router.afterEach(async (to, from) => {
  document.title = String(to.meta.title ?? 'ColdSafe')
  if (!from.name || to.name === from.name) return
  await nextTick()
  document.querySelector<HTMLElement>('main h1')?.focus()
})

export default router
