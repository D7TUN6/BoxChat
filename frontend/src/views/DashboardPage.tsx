import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Divider,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { CirclePlus, MessageSquare, Server, User } from 'lucide-react'

type Room = {
  id: number
  name: string
  type: string
  channels?: { id: number; name: string }[]
  avatar_url?: string | null
}

export default function DashboardPage() {
  const [rooms, setRooms] = useState<Room[]>([])
  const [error, setError] = useState<string | null>(null)
  const [incomingRequests, setIncomingRequests] = useState<Array<{ id: number; user?: { id?: number; username?: string } }>>([])

  useEffect(() => {
    let active = true
    async function loadData() {
      const response = await fetch('/api/v1/rooms', {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null)
      if (!response?.ok || !active) {
        if (active) setError('Could not load rooms')
        return
      }
      const payload = await response.json().catch(() => null)
      if (active) setRooms(payload?.rooms ?? [])
    }
    void loadData()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    async function loadRequests() {
      const res = await fetch('/api/v1/friends/requests', {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null)
      if (!res?.ok || !active) return
      const payload = await res.json().catch(() => null)
      if (!active) return
      setIncomingRequests(Array.isArray(payload?.incoming) ? payload.incoming : [])
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

  const dms = useMemo(() => rooms.filter((r) => r.type === 'dm'), [rooms])
  const servers = useMemo(() => rooms.filter((r) => r.type !== 'dm'), [rooms])

  return (
    <Stack spacing={1.6}>
      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 2 }}>
        <Typography variant="h5" fontWeight={800}>
          Welcome
        </Typography>
        <Typography color="text.secondary">Select a server or start a conversation</Typography>
      </Paper>

      {error ? <Alert severity="warning">{error}</Alert> : null}

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 1.2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 0.6, py: 0.4 }}>
          <Typography variant="subtitle1" fontWeight={700}>
            Friend Requests
          </Typography>
          <Button href="/notifications" size="small">
            Open notifications
          </Button>
        </Stack>
        <Divider sx={{ mb: 0.8 }} />
        <Stack spacing={0.6}>
          {!incomingRequests.length ? (
            <Typography color="text.secondary" sx={{ px: 1.1, py: 0.6 }}>
              No incoming requests.
            </Typography>
          ) : (
            incomingRequests.map((req) => (
              <Stack
                key={`fr-${req.id}`}
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, px: 1, py: 0.8 }}
              >
                <Typography noWrap sx={{ minWidth: 0, pr: 1 }}>
                  {req.user?.username ?? 'Unknown'} sent a friend request
                </Typography>
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
              </Stack>
            ))
          )}
        </Stack>
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 1.2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 0.6, py: 0.4 }}>
          <Typography variant="subtitle1" fontWeight={700}>
            Direct Messages
          </Typography>
          <Button href="/explore" size="small" startIcon={<CirclePlus size={16} />}>
            Start DM
          </Button>
        </Stack>
        <Divider sx={{ mb: 0.8 }} />
        <Stack spacing={0.4}>
          {dms.length ? (
            dms.map((room) => (
              <Button
                key={`dm-${room.id}`}
                href={`/room/${room.id}${room.channels?.[0] ? `?channel_id=${room.channels[0].id}` : ''}`}
                color="inherit"
                sx={{ justifyContent: 'flex-start', py: 1, px: 1, borderRadius: 2 }}
                startIcon={<User size={16} />}
              >
                <Box sx={{ textAlign: 'left', minWidth: 0 }}>
                  <Typography noWrap fontWeight={600}>
                    {room.name}
                  </Typography>
                </Box>
              </Button>
            ))
          ) : (
            <Typography color="text.secondary" sx={{ px: 1.1, py: 0.6, display: 'flex', alignItems: 'center', gap: 0.7 }}>
              <MessageSquare size={15} />
              No direct messages yet.
            </Typography>
          )}
        </Stack>
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 1.2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 0.6, py: 0.4 }}>
          <Typography variant="subtitle1" fontWeight={700}>
            Servers
          </Typography>
          <Button href="/explore" size="small" startIcon={<CirclePlus size={16} />}>
            Join
          </Button>
        </Stack>
        <Divider sx={{ mb: 0.8 }} />
        <Stack spacing={0.4}>
          {servers.length ? (
            servers.map((room) => (
              <Button
                key={`server-${room.id}`}
                href={`/room/${room.id}${room.channels?.[0] ? `?channel_id=${room.channels[0].id}` : ''}`}
                color="inherit"
                sx={{ justifyContent: 'flex-start', py: 1, px: 1, borderRadius: 2 }}
                startIcon={
                  room.avatar_url ? (
                    <Avatar src={room.avatar_url} sx={{ width: 22, height: 22 }} />
                  ) : (
                    <Server size={16} />
                  )
                }
              >
                <Box sx={{ textAlign: 'left', minWidth: 0 }}>
                  <Typography noWrap fontWeight={600}>
                    {room.name}
                  </Typography>
                </Box>
              </Button>
            ))
          ) : (
            <Typography color="text.secondary" sx={{ px: 1.1, py: 0.6 }}>
              No servers yet.
            </Typography>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}
