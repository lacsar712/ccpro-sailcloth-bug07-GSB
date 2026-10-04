<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const showNav = computed(() => route.name !== 'login')

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div v-if="!showNav">
    <router-view />
  </div>
  <div v-else class="layout">
    <aside class="side">
      <div class="brand">
        <span class="mark">帆</span>
        <strong>SailCloth</strong>
        <small>浸渍防水台</small>
      </div>
      <nav>
        <router-link to="/">晾晒架</router-link>
      </nav>
      <div class="nav-secondary">
        <p class="nav-sec-label">台账（次要）</p>
        <router-link to="/rolls">布卷台账</router-link>
        <router-link to="/dips">浸渍台账</router-link>
      </div>
      <button class="linkish" type="button" @click="logout">退出 {{ auth.user?.username }}</button>
    </aside>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>
