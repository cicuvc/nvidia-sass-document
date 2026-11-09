import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import ArchView from './views/ArchView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { title: 'NVIDIA SASS ISA' },
    },
    {
      path: '/arch/:arch/:slug?',
      name: 'arch',
      component: ArchView,
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.params.slug !== from.params.slug) return { top: 0 }
    return undefined
  },
})

router.afterEach((to) => {
  const mnemonic = to.params.slug
    ? String(to.params.slug).replaceAll('-', ' ').toUpperCase()
    : ''
  const arch = to.params.arch ? String(to.params.arch).toUpperCase() : ''
  document.title = mnemonic
    ? `${mnemonic} · ${arch} · NVIDIA SASS ISA`
    : 'NVIDIA SASS ISA'
})

export default router
