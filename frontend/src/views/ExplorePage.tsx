import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Grid,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Compass, Search, Server, UserPlus } from 'lucide-react'

type FoundServer = {
  id: number
  name: string
  avatar_url?: string | null
  description?: string
  member_count?: number
  type?: string
}

export default function ExplorePage() {
  const [q, setQ] = useState('')
  const [servers, setServers] = useState<FoundServer[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [friendUsername, setFriendUsername] = useState('')
  const [friendMessage, setFriendMessage] = useState<string | null>(null)
  const [sendingInvite, setSendingInvite] = useState(false)

  async function runSearch(queryOverride?: string) {
    const query = (queryOverride ?? q).trim()
    setLoading(true)
    setError(null)
    try {
      const serverRes = await fetch(`/api/v1/search/servers?q=${encodeURIComponent(query)}`, {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      })

      const serversPayload = await serverRes.json().catch(() => ({}))
      setServers(Array.isArray(serversPayload.servers) ? serversPayload.servers : [])
    } catch {
      setError('Search failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void runSearch('')
  }, [])

  useEffect(() => {
    if (!friendMessage) return
    const t = window.setTimeout(() => setFriendMessage(null), 4500)
    return () => window.clearTimeout(t)
  }, [friendMessage])

  async function sendFriendInvite() {
    const username = friendUsername.trim()
    if (!username || sendingInvite) return
    setSendingInvite(true)
    setFriendMessage(null)
    setError(null)
    try {
      const res = await fetch('/api/v1/friends/request', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ username }),
      })
      const payload = await res.json().catch(() => null)
      if (!res.ok) throw new Error(payload?.error ?? 'Invite failed')
      setFriendMessage(payload?.status === 'already_friends'
        ? 'Already friends'
        : payload?.status === 'pending'
          ? 'Request already pending'
          : 'Friend request sent'
      )
      setFriendUsername('')
    } catch (e: any) {
      setError(e?.message ?? 'Invite failed')
    } finally {
      setSendingInvite(false)
    }
  }

  async function joinServer(serverId: number) {
    const res = await fetch(`/api/v1/room/${serverId}/join`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    })
    if (!res.ok) return
    window.location.href = `/room/${serverId}`
  }

  const featuredServers = useMemo(() => servers.slice(0, 12), [servers])

  return (
    <Stack spacing={2.2}>
      {error ? <Alert severity="warning">{error}</Alert> : null}
      {friendMessage ? <Alert severity="success">{friendMessage}</Alert> : null}

      <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider' }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} mb={1.2}>
            <UserPlus size={18} />
            <Typography variant="h6">Add friend</Typography>
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              fullWidth
              value={friendUsername}
              onChange={(e) => setFriendUsername(e.target.value)}
              placeholder="Enter username"
            />
            <Button variant="contained" onClick={() => void sendFriendInvite()} disabled={sendingInvite || !friendUsername.trim()}>
              {sendingInvite ? 'Sending...' : 'Send invite'}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider' }}>
        <CardContent>
          <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1} mb={1.2}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Compass size={18} />
              <Box>
                <Typography variant="h6" fontWeight={900}>Discover servers</Typography>
                <Typography variant="caption" color="text.secondary">
                  Найдите сообщества по названию и присоединяйтесь.
                </Typography>
              </Box>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {servers.length} results
            </Typography>
          </Stack>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              fullWidth
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search servers"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void runSearch()
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search size={16} />
                  </InputAdornment>
                ),
              }}
            />
            <Button
              variant="contained"
              onClick={() => void runSearch()}
              disabled={loading}
              startIcon={<Server size={16} />}
              sx={{ minWidth: { xs: '100%', sm: 140 } }}
            >
              {loading ? 'Searching...' : 'Search'}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        {featuredServers.map((s: FoundServer) => (
          <Grid key={s.id} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
            <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider', height: '100%' }}>
              <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.2 }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Avatar src={s.avatar_url ?? undefined} sx={{ width: 44, height: 44 }}>
                    {s.name.slice(0, 2).toUpperCase()}
                  </Avatar>
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography fontWeight={900} noWrap>
                      {s.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {(s.member_count ?? 0)} members · {s.type ?? 'server'}
                    </Typography>
                  </Box>
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40 }}>
                  {s.description ? s.description.slice(0, 70) : ' '}
                </Typography>
                <Box sx={{ flex: 1 }} />
                <Button variant="contained" onClick={() => void joinServer(s.id)}>
                  Join
                </Button>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Stack>
  )
}
