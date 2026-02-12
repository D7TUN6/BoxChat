export type AppNotification = {
  id: string
  createdAt: number
  title: string
  body: string
  href?: string
  read: boolean
  dedupeKey?: string
}

export type NotificationPermissionState = 'unsupported' | 'default' | 'denied' | 'granted'

const KEY = 'bc_notifications_v1'
const EVT = 'bc_notifications_changed'
const AUDIO_UNLOCK_KEY = 'bc_audio_unlocked_v1'

let audioCtx: AudioContext | null = null

function ensureAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!('AudioContext' in window || 'webkitAudioContext' in window)) return null
  if (!audioCtx) {
    const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext
    audioCtx = new Ctx()
  }
  return audioCtx
}

function safeParse(raw: string | null): AppNotification[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed as AppNotification[]
  } catch {
    return []
  }
}

function normalizeHref(href?: string): string {
  if (!href) return ''
  try {
    const u = new URL(href, window.location.origin)
    return `${u.pathname}${u.search}`
  } catch {
    return String(href)
  }
}

export function getNotifications(): AppNotification[] {
  const list = safeParse(localStorage.getItem(KEY))
  const filtered = list.filter((n) => !n.read)
  if (filtered.length !== list.length) {
    localStorage.setItem(KEY, JSON.stringify(filtered))
  }
  return filtered
}

export function getUnreadCount(): number {
  return getNotifications().filter((n) => !n.read).length
}

export function addNotification(n: Omit<AppNotification, 'id' | 'createdAt' | 'read'>): AppNotification {
  const list = getNotifications()
  if (n.dedupeKey) {
    const existing = list.find((x) => x.dedupeKey === n.dedupeKey)
    if (existing) return existing
  }

  const full: AppNotification = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    createdAt: Date.now(),
    read: false,
    ...n,
  }

  list.unshift(full)
  localStorage.setItem(KEY, JSON.stringify(list.slice(0, 200)))
  window.dispatchEvent(new CustomEvent(EVT))
  return full
}

export function markAllRead(): void {
  localStorage.setItem(KEY, JSON.stringify([]))
  window.dispatchEvent(new CustomEvent(EVT))
}

export function markRead(id: string): void {
  const list = getNotifications().filter((n) => n.id !== id)
  localStorage.setItem(KEY, JSON.stringify(list))
  window.dispatchEvent(new CustomEvent(EVT))
}

export function clearNotificationsByHref(href: string): void {
  const target = normalizeHref(href)
  if (!target) return
  const list = getNotifications().filter((n) => normalizeHref(n.href) !== target)
  localStorage.setItem(KEY, JSON.stringify(list))
  window.dispatchEvent(new CustomEvent(EVT))
}

export function subscribeNotifications(cb: () => void): () => void {
  const handler = () => cb()
  window.addEventListener(EVT, handler as EventListener)
  window.addEventListener('storage', handler)
  return () => {
    window.removeEventListener(EVT, handler as EventListener)
    window.removeEventListener('storage', handler)
  }
}

export function getBrowserNotificationPermission(): NotificationPermissionState {
  if (typeof window === 'undefined') return 'unsupported'
  if (!('Notification' in window)) return 'unsupported'
  return Notification.permission
}

export async function requestBrowserNotificationPermission(): Promise<NotificationPermissionState> {
  const state = getBrowserNotificationPermission()
  if (state === 'unsupported') return state
  if (state !== 'default') return state
  try {
    const res = await Notification.requestPermission()
    return res
  } catch {
    return getBrowserNotificationPermission()
  }
}

export function unlockAudio(): void {
  try {
    const ctx = ensureAudioContext()
    if (!ctx) return
    if (ctx.state === 'suspended') {
      void ctx.resume()
    }
    localStorage.setItem(AUDIO_UNLOCK_KEY, '1')
  } catch {
    // ignore
  }
}

export function playNotificationSound(): void {
  try {
    if (typeof window === 'undefined') return
    const ctx = ensureAudioContext()
    if (!ctx) return
    if (ctx.state === 'suspended') {
      void ctx.resume()
    }
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0, ctx.currentTime)
    gain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.2)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.22)
  } catch {
    // ignore
  }
}

export function showBrowserNotification(title: string, body: string, href?: string): void {
  if (typeof window === 'undefined') return
  if (!('Notification' in window)) return
  if (Notification.permission !== 'granted') return

  try {
    const n = new Notification(title, { body })
    n.onclick = () => {
      try {
        window.focus()
        if (href) window.location.href = href
      } catch {
        // ignore
      }
    }
  } catch {
    // ignore
  }
}
