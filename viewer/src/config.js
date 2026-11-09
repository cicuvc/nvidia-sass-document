export const REPO_URL = 'https://github.com/cicuvc/nvidia-sass-document'
export const REPO_REF =
  import.meta.env.VITE_GIT_REF || 'notes/consolidate-phase0-3'

export function githubFileUrl(path) {
  if (!path) return REPO_URL
  return `${REPO_URL}/blob/${REPO_REF}/${path.replace(/^\/+/, '')}`
}
