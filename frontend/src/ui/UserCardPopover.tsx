import { Alert, Avatar, Box, Button, Paper, Popover, Stack, Typography } from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

type RoleLike = {
  id: number
  name: string
  mention_tag: string
}

export type MemberLike = {
  id: number
  username: string
  avatar_url?: string | null
  role?: string | null
  role_ids?: number[]
  presence_status?: string | null
}

export default function UserCardPopover({
  anchorEl,
  userId,
  members,
  roomRoles,
  roomId,
  myRole,
  currentUserId,
  onActionDone,
  onClose,
}: {
  anchorEl: HTMLElement | null
  userId: number | null
  members: MemberLike[]
  roomRoles?: RoleLike[]
  roomId?: number | null
  myRole?: string | null
  currentUserId?: number | null
  onActionDone?: () => void
  onClose: () => void
}) {
  const user = useMemo(() => {
    if (!userId) return null
    return members.find((m) => Number(m.id) === Number(userId)) || null
  }, [members, userId])

  const roleNames = useMemo(() => {
    if (!user) return []
    const roleMap = new Map<number, RoleLike>()
    for (const r of roomRoles || []) roleMap.set(Number(r.id), r)
    const ids = Array.isArray(user.role_ids) ? user.role_ids : []
    const names = ids
      .map((id) => roleMap.get(Number(id)))
      .filter((r): r is RoleLike => Boolean(r))
      .filter((r) => r.mention_tag !== 'everyone')
      .sort((a, b) => Number(b.id) - Number(a.id))
      .map((r) => r.name)

    if (names.length) return names
    if (user.role && user.role !== 'member') return [user.role]
    return []
  }, [user, roomRoles])

  const myRank = myRole === 'owner' ? 3 : myRole === 'admin' ? 2 : 1
  const targetRole = user?.role || 'member'
  const targetRank = targetRole === 'owner' ? 3 : targetRole === 'admin' ? 2 : 1
  const canModerate = Boolean(
    roomId &&
    currentUserId &&
    user &&
    Number(user.id) !== Number(currentUserId) &&
    myRank > targetRank &&
    myRank >= 2,
  )
  const canSendFriendRequest = Boolean(user && currentUserId && Number(user.id) !== Number(currentUserId))
  const [friendActionText, setFriendActionText] = useState<string | null>(null)
  const [friendshipKnown, setFriendshipKnown] = useState<'unknown' | 'friends' | 'pending' | 'none'>('unknown')
  const [friendSending, setFriendSending] = useState(false)

  useEffect(() => {
    setFriendActionText(null)
    setFriendshipKnown('unknown')
    setFriendSending(false)
  }, [userId])

  useEffect(() => {
    let active = true
    const targetUserId = user?.id
    if (!targetUserId || !canSendFriendRequest) return () => { active = false }

    async function loadFriendStatus() {
      const res = await fetch(`/api/v1/friends/status/${targetUserId}`, {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null)
      const payload = await res?.json().catch(() => null)
      if (!active) return
      if (!res?.ok) {
        setFriendshipKnown('unknown')
        return
      }
      const status = String(payload?.status || 'none')
      if (status === 'friends') {
        setFriendshipKnown('friends')
        setFriendActionText('You are already friends')
      } else if (status === 'pending') {
        setFriendshipKnown('pending')
        const direction = String(payload?.direction || '')
        setFriendActionText(direction === 'incoming' ? 'Incoming friend request' : 'Friend request already pending')
      } else {
        setFriendshipKnown('none')
        setFriendActionText(null)
      }
    }
    void loadFriendStatus()
    return () => {
      active = false
    }
  }, [user?.id, canSendFriendRequest])

  async function doKick() {
    if (!roomId || !user) return
    await fetch(`/admin/user/${user.id}/kick_from_room/${roomId}`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(() => null)
    onActionDone?.()
    onClose()
  }

  async function doBan() {
    if (!roomId || !user) return
    await fetch(`/admin/user/${user.id}/ban`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ room_id: roomId, reason: 'Moderation action' }),
    }).catch(() => null)
    onActionDone?.()
    onClose()
  }

  async function sendFriendRequest() {
    if (!user || !canSendFriendRequest || friendSending) return
    setFriendSending(true)
    setFriendActionText(null)
    const res = await fetch('/api/v1/friends/request', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ username: user.username }),
    }).catch(() => null)
    const payload = await res?.json().catch(() => null)
    if (!res?.ok) {
      setFriendActionText(String(payload?.error || 'Failed to send request'))
      setFriendSending(false)
      return
    }
    const status = String(payload?.status || '')
    if (status === 'already_friends') {
      setFriendshipKnown('friends')
      setFriendActionText('You are already friends')
    } else if (status === 'pending') {
      setFriendshipKnown('pending')
      setFriendActionText('Friend request already pending')
    } else {
      setFriendshipKnown('none')
      setFriendActionText('Friend request sent')
    }
    setFriendSending(false)
  }

  async function openDm() {
    if (!user) return
    const res = await fetch(`/api/v1/dm/${user.id}/create`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(() => null)
    const payload = await res?.json().catch(() => null)
    const dmRoomId = Number(payload?.room_id || 0)
    if (dmRoomId > 0) {
      window.location.href = `/room/${dmRoomId}`
      return
    }
    setFriendActionText(String(payload?.error || 'Failed to open DM'))
  }

  return (
    <Popover
      open={Boolean(anchorEl && userId)}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      transformOrigin={{ vertical: 'top', horizontal: 'left' }}
      PaperProps={{ sx: { borderRadius: 3, width: 320, overflow: 'hidden' } }}
    >
      <Box sx={{ height: 54, bgcolor: 'background.default' }} />
      <Box sx={{ px: 2, pb: 2, pt: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1.2, mt: -3 }}>
          <Avatar
            src={user?.avatar_url ?? undefined}
            sx={{ width: 56, height: 56, border: '4px solid', borderColor: 'background.paper' }}
          >
            {(user?.username || '?').slice(0, 2).toUpperCase()}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0, pb: 0.6 }}>
            <Typography sx={{ fontWeight: 900, fontSize: 18 }} noWrap>
              {user?.username ?? 'User'}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {user?.presence_status ? `Status: ${user.presence_status}` : ''}
            </Typography>
          </Box>
        </Box>

        <Paper elevation={0} sx={{ mt: 1.2, p: 1.2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 900, letterSpacing: 0.6, textTransform: 'uppercase' }}>
            Profile
          </Typography>
          <Stack direction="row" spacing={0.8} flexWrap="wrap" useFlexGap sx={{ mt: 0.8 }}>
            {roleNames.length ? (
              roleNames.map((name) => (
                <Box
                  key={`role-${name}`}
                  sx={{
                    px: 1,
                    py: 0.35,
                    borderRadius: 999,
                    border: '1px solid',
                    borderColor: 'divider',
                    fontSize: 13,
                    fontWeight: 700,
                  }}
                >
                  {name}
                </Box>
              ))
            ) : (
              <Typography sx={{ fontWeight: 700 }} color="text.secondary">member</Typography>
            )}
          </Stack>
        </Paper>

        {canSendFriendRequest ? (
          <Paper elevation={0} sx={{ mt: 1.2, p: 1.2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 900, letterSpacing: 0.6, textTransform: 'uppercase' }}>
              Actions
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              {friendshipKnown !== 'friends' ? (
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => void sendFriendRequest()}
                  disabled={friendSending || friendshipKnown === 'pending'}
                >
                  {friendSending ? 'Sending...' : (friendshipKnown === 'pending' ? 'Pending' : 'Add friend')}
                </Button>
              ) : null}
              {friendshipKnown === 'friends' ? (
                <Button size="small" variant="outlined" onClick={() => void openDm()}>
                  Write
                </Button>
              ) : null}
            </Stack>
            {friendActionText ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.8 }}>
                {friendActionText}
              </Typography>
            ) : null}
          </Paper>
        ) : null}

        {canModerate ? (
          <Paper elevation={0} sx={{ mt: 1.2, p: 1.2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 900, letterSpacing: 0.6, textTransform: 'uppercase' }}>
              Moderation
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              <Button size="small" color="warning" variant="outlined" onClick={() => void doKick()}>
                Kick
              </Button>
              <Button size="small" color="error" variant="outlined" onClick={() => void doBan()}>
                Ban
              </Button>
            </Stack>
          </Paper>
        ) : null}
        {!user ? <Alert severity="info" sx={{ mt: 1.2 }}>User not found</Alert> : null}
      </Box>
    </Popover>
  )
}
