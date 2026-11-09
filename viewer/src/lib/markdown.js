import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { githubFileUrl } from '../config'

marked.setOptions({
  gfm: true,
  breaks: false,
})

function normalizePath(path) {
  const parts = []
  for (const part of path.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') parts.pop()
    else parts.push(part)
  }
  return parts.join('/')
}

function resolveRepoPath(notePath, href) {
  const [target, hash = ''] = href.split('#', 2)
  if (!target) return ''
  const dir = notePath.includes('/')
    ? notePath.slice(0, notePath.lastIndexOf('/'))
    : ''
  return normalizePath(`${dir}/${target}`) + (hash ? `#${hash}` : '')
}

export function renderMarkdown(markdown, notePath = '') {
  if (!markdown) return ''
  const raw = marked.parse(markdown)
  const doc = new DOMParser().parseFromString(raw, 'text/html')

  for (const anchor of doc.querySelectorAll('a[href]')) {
    const href = anchor.getAttribute('href') || ''
    if (!href || href.startsWith('#') || /^[a-z]+:/i.test(href)) {
      if (/^https?:/i.test(href)) {
        anchor.setAttribute('target', '_blank')
        anchor.setAttribute('rel', 'noreferrer')
      }
      continue
    }
    const resolved = resolveRepoPath(notePath, href)
    anchor.setAttribute('href', githubFileUrl(resolved))
    anchor.setAttribute('target', '_blank')
    anchor.setAttribute('rel', 'noreferrer')
  }

  return DOMPurify.sanitize(doc.body.innerHTML, {
    ADD_ATTR: ['target', 'rel'],
  })
}
