import { useEffect, useMemo, useState } from 'react'
import { Box, Button, Divider, Paper, Stack, Typography } from '@mui/material'
import { markAllRead, getNotifications, markRead, subscribeNotifications, type AppNotification } from '../ui/notificationsStore'

function formatTime(ts: number): string {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ''
  }
}

type FriendRequestItem = {
  id: number
  direction: 'incoming' | 'outgoing'
  status: string
  created_at?: string | null
  user?: {
    id: number
    username: string
    avatar_url?: string | null
  }
}

export default function NotificationsPage() {
  const [items, setItems] = useState<AppNotification[]>(() => getNotifications())
  const [incomingRequests, setIncomingRequests] = useState<FriendRequestItem[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)

  useEffect(() => {
    return subscribeNotifications(() => setItems(getNotifications()))
  }, [])

  useEffect(() => {
    let active = true
    async function loadRequests() {
      setRequestsLoading(true)
      setRequestError(null)
      const res = await fetch('/api/v1/friends/requests', {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null)
      if (!res?.ok) {
        if (active) setRequestError('Failed to load friend requests')
        if (active) setRequestsLoading(false)
        return
      }
      const payload = await res.json().catch(() => null)
      if (!active) return
      setIncomingRequests(Array.isArray(payload?.incoming) ? payload.incoming : [])
      setRequestsLoading(false)
    }
    void loadRequests()
    const timer = window.setInterval(() => {
      void loadRequests()
    }, 10000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  async function respondToRequest(requestId: number, action: 'accept' | 'decline', otherUserId?: number) {
    const res = await fetch(`/api/v1/friends/requests/${requestId}/respond`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ action }),
    }).catch(() => null)
    if (!res?.ok) return
    setIncomingRequests((prev) => prev.filter((r) => Number(r.id) !== Number(requestId)))
    if (action === 'accept' && otherUserId) {
      const dmRes = await fetch(`/api/v1/dm/${otherUserId}/create`, {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null)
      const payload = await dmRes?.json().catch(() => null)
      const roomId = Number(payload?.room_id || 0)
      if (roomId > 0) {
        window.location.href = `/room/${roomId}`
      }
    }
  }

  const unread = useMemo(() => items.filter((i) => !i.read).length, [items])

  return (
    <Stack spacing={1.2} sx={{ height: '100%', minHeight: 0 }}>
      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 1.4 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="h6" fontWeight={900}>
              Notifications
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Unread: {unread}
            </Typography>
          </Box>
          <Button
            size="small"
            onClick={() => markAllRead()}
            disabled={!unread}
            variant="contained"
          >
            Mark all read
          </Button>
        </Stack>
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 1.2 }}>
        <Typography variant="subtitle1" fontWeight={800} sx={{ mb: 0.8 }}>
          Friend Requests
        </Typography>
        {requestError ? (
          <Typography color="warning.main" sx={{ px: 0.4, py: 0.2 }}>
            {requestError}
          </Typography>
        ) : null}
        {requestsLoading && !incomingRequests.length ? (
          <Typography color="text.secondary" sx={{ px: 0.4, py: 0.2 }}>
            Loading...
          </Typography>
        ) : null}
        {!incomingRequests.length && !requestsLoading ? (
          <Typography color="text.secondary" sx={{ px: 0.4, py: 0.2 }}>
            No incoming requests.
          </Typography>
        ) : null}
        <Stack spacing={0.8}>
          {incomingRequests.map((req) => (
            <Box
              key={req.id}
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 2,
                px: 1,
                py: 0.9,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1,
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Typography fontWeight={700} noWrap>
                  {req.user?.username ?? 'Unknown'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  wants to be your friend
                </Typography>
              </Box>
              <Stack direction="row" spacing={0.6}>
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => void respondToRequest(req.id, 'accept', req.user?.id)}
                >
                  Accept
                </Button>
                <Button size="small" variant="outlined" color="inherit" onClick={() => void respondToRequest(req.id, 'decline')}>
                  Decline
                </Button>
              </Stack>
            </Box>
          ))}
        </Stack>
      </Paper>

      <Paper elevation={0} className="bc-scroll" sx={{ border: '1px solid', borderColor: 'divider', overflow: 'hidden', flex: 1, minHeight: 0 }}>
        <Box className="bc-scroll" sx={{ overflowY: 'auto', height: '100%' }}>
          {!items.length ? (
            <Typography color="text.secondary" sx={{ p: 2 }}>
              No notifications.
            </Typography>
          ) : null}

          {items.map((n, idx) => (
            <Box key={n.id}>
              <Box
                role="button"
                tabIndex={0}
                onClick={() => {
                  markRead(n.id)
                  if (n.href) window.location.href = n.href
                }}
                sx={{
                  p: 1.4,
                  cursor: n.href ? 'pointer' : 'default',
                  bgcolor: n.read ? 'transparent' : 'rgba(88,101,242,.12)',
                  '&:hover': { bgcolor: n.read ? 'rgba(255,255,255,.04)' : 'rgba(88,101,242,.16)' },
                }}
              >
                <Stack spacing={0.2}>
                  <Typography fontWeight={900} noWrap>
                    {n.title}
                  </Typography>
                  <Typography color="text.secondary" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {n.body}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatTime(n.createdAt)}
                  </Typography>
                </Stack>
              </Box>
              {idx !== items.length - 1 ? <Divider /> : null}
            </Box>
          ))}
        </Box>
      </Paper>
    </Stack>
  )
}
