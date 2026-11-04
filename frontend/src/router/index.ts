import { createRouter, createWebHistory } from 'vue-router'
import { focusPageHeading } from '../features/navigation/navigation'
import { safeInternalRedirect } from './redirect'
import { sessionToken } from '../features/account/session'
import { installDraftProtection } from '../features/editing/draft-protection'

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
      meta: { requiresAuth: true, area: 'monitoring', contentId: 'dashboard-title', title: 'Visão geral · ColdSafe' }
    },
    {
      path: '/digital-twin',
      name: 'digital-twin',
      component: () => import('../views/DigitalTwinView.vue'),
      meta: { requiresAuth: true, area: 'monitoring', contentId: 'digital-twin-title', title: 'Gêmeo digital · ColdSafe' }
    },
    {
      path: '/insights',
      name: 'insights',
      component: () => import('../views/InsightsView.vue'),
      meta: { requiresAuth: true, area: 'monitoring', contentId: 'insights-title', title: 'Saúde e previsões · ColdSafe' }
    },
    {
      path: '/assistant',
      name: 'assistant',
      component: () => import('../views/AssistantView.vue'),
      meta: { requiresAuth: true, contentId: 'assistant-title', title: 'Assistente · ColdSafe' }
    },
    {
      path: '/laboratory',
      name: 'laboratory',
      component: () => import('../views/LaboratoryView.vue'),
      meta: { requiresAuth: true, area: 'data', contentId: 'laboratory-title', requiresAdmin: true, title: 'Dados sintéticos · ColdSafe' }
    },
    {
      path: '/training',
      name: 'training',
      component: () => import('../views/TrainingView.vue'),
      meta: { requiresAuth: true, area: 'data', contentId: 'training-title', requiresAdmin: true, title: 'Treinamento de modelos · ColdSafe' }
    },
    {
      path: '/messaging',
      name: 'messaging',
      component: () => import('../views/MessagingView.vue'),
      meta: { requiresAuth: true, area: 'messaging', contentId: 'messaging-title', requiresAdmin: true, title: 'Filas e mensagens · ColdSafe' }
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
      meta: { requiresAuth: true, area: 'manage', contentId: 'manage-title', title: 'Ambientes e dispositivos · ColdSafe' }
    }
  ]
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !sessionToken.value) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && sessionToken.value) return safeInternalRedirect(to.query.redirect)
})

installDraftProtection(router)

router.afterEach(async (to, from, failure) => {
  if (failure) return
  document.title = String(to.meta.title ?? 'ColdSafe')
  if (!from.name || to.name === from.name) return
  await focusPageHeading()
})

export default router
