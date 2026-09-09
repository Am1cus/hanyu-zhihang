import { createRouter, createWebHistory } from 'vue-router'
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '飞行监测' } },
    { path: '/experiments', component: () => import('@/views/Experiments.vue'), meta: { title: '实验验证' } },
    { path: '/warning', component: () => import('@/views/WarningCenter.vue'), meta: { title: '预警记录' } },
    // Old URLs resolve to working pages; unfinished source modules remain in the repository.
    { path: '/battery', redirect: '/experiments' },
    { path: '/data-analysis', redirect: '/experiments' },
    { path: '/drone', redirect: '/dashboard' },
    { path: '/flight-plan', redirect: '/dashboard' },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
  ],
  scrollBehavior: () => ({ top: 0 })
})
router.beforeEach(to => { document.title = to.meta.title + ' · 寒域智航' })
export default router
