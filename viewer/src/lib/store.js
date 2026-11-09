import { reactive, readonly } from 'vue'

const state = reactive({
  manifest: null,
  loading: false,
  error: '',
  detailCache: new Map(),
})

const dataRoot = new URL('data/', document.baseURI)

async function fetchJson(path) {
  const response = await fetch(new URL(path, dataRoot))
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${path}`)
  }
  return response.json()
}

export async function ensureManifest() {
  if (state.manifest) return state.manifest
  if (state.loading) {
    while (state.loading) {
      await new Promise((resolve) => setTimeout(resolve, 25))
    }
    return state.manifest
  }
  state.loading = true
  state.error = ''
  try {
    state.manifest = await fetchJson('manifest.json')
    return state.manifest
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error)
    throw error
  } finally {
    state.loading = false
  }
}

export async function loadInstruction(arch, slug) {
  const key = `${arch}/${slug}`
  if (state.detailCache.has(key)) return state.detailCache.get(key)
  const pending = fetchJson(`details/${arch}/${slug}.json`)
  state.detailCache.set(key, pending)
  try {
    return await pending
  } catch (error) {
    state.detailCache.delete(key)
    throw error
  }
}

export function findArchitecture(arch) {
  return state.manifest?.architectures.find((item) => item.id === arch) || null
}

export function findInstruction(arch, slug) {
  return findArchitecture(arch)?.instructions.find((item) => item.slug === slug) || null
}

export const viewerState = readonly(state)
