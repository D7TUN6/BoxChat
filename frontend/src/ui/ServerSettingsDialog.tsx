import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'

type PermissionKey =
  | 'manage_server'
  | 'manage_roles'
  | 'manage_channels'
  | 'invite_members'
  | 'delete_server'
  | 'delete_messages'
  | 'kick_members'
  | 'ban_members'
  | 'mute_members'

type Role = {
  id: number
  name: string
  mention_tag: string
  is_system?: boolean
  can_be_mentioned_by_everyone?: boolean
  allowed_source_role_ids?: number[]
  permissions?: PermissionKey[]
}

type Member = {
  id: number
  username: string
  role?: string
  avatar_url?: string | null
  role_ids?: number[]
  muted_until?: string | null
}

type ChannelSummary = {
  id: number
  name: string
  writer_role_ids?: number[]
}

type RoomSettingsPayload = {
  id: number
  name: string
  description?: string
  type: string
  owner_id?: number
  is_public?: boolean
  avatar_url?: string | null
  banner_url?: string | null
  permissions?: {
    can_manage_server?: boolean
    can_manage_roles?: boolean
    can_manage_channels?: boolean
    can_invite_members?: boolean
    can_delete_server?: boolean
    can_delete_messages?: boolean
    can_kick_members?: boolean
    can_ban_members?: boolean
    can_mute_members?: boolean
    granted_permissions?: PermissionKey[]
  }
}

const ROLE_PERMISSION_OPTIONS: Array<{ key: PermissionKey; label: string }> = [
  { key: 'manage_server', label: 'Manage server' },
  { key: 'manage_roles', label: 'Manage roles' },
  { key: 'manage_channels', label: 'Manage channels' },
  { key: 'invite_members', label: 'Invite members' },
  { key: 'delete_server', label: 'Delete server' },
  { key: 'delete_messages', label: 'Delete messages' },
  { key: 'kick_members', label: 'Kick members' },
  { key: 'ban_members', label: 'Ban members' },
  { key: 'mute_members', label: 'Mute members' },
]

export default function ServerSettingsDialog({
  open,
  onClose,
  roomId,
}: {
  open: boolean
  onClose: () => void
  roomId: number
}) {
  const [tab, setTab] = useState(0)
  const [settings, setSettings] = useState<RoomSettingsPayload | null>(null)
  const [roles, setRoles] = useState<Role[]>([])
  const [members, setMembers] = useState<Member[]>([])
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const [nameDraft, setNameDraft] = useState('')
  const [descriptionDraft, setDescriptionDraft] = useState('')
  const [isPublicDraft, setIsPublicDraft] = useState(false)
  const [newRoleName, setNewRoleName] = useState('')

  const [roleNameDrafts, setRoleNameDrafts] = useState<Record<number, string>>({})
  const [roleMentionEveryoneDrafts, setRoleMentionEveryoneDrafts] = useState<Record<number, boolean>>({})
  const [roleMentionersDrafts, setRoleMentionersDrafts] = useState<Record<number, number[]>>({})
  const [rolePermissionDrafts, setRolePermissionDrafts] = useState<Record<number, PermissionKey[]>>({})
  const [memberRoleDrafts, setMemberRoleDrafts] = useState<Record<number, number[]>>({})
  const [channelWriterRoleDrafts, setChannelWriterRoleDrafts] = useState<Record<number, number[]>>({})

  const [deleteConfirmChecked, setDeleteConfirmChecked] = useState(false)

  const avatarInputRef = useRef<HTMLInputElement | null>(null)
  const bannerInputRef = useRef<HTMLInputElement | null>(null)

  const canManageServer = Boolean(settings?.permissions?.can_manage_server)
  const canManageRoles = Boolean(settings?.permissions?.can_manage_roles)
  const canManageChannels = Boolean(settings?.permissions?.can_manage_channels)
  const canDeleteServer = Boolean(settings?.permissions?.can_delete_server)
  const canKickMembers = Boolean(settings?.permissions?.can_kick_members)
  const canBanMembers = Boolean(settings?.permissions?.can_ban_members)
  const canMuteMembers = Boolean(settings?.permissions?.can_mute_members)
  const canModerateMembers = canKickMembers || canBanMembers || canMuteMembers

  const rolesById = useMemo(() => {
    const m = new Map<number, Role>()
    for (const r of roles) m.set(Number(r.id), r)
    return m
  }, [roles])

  function displayRolesForMember(m: Member): string {
    const ids = Array.isArray(m.role_ids) ? m.role_ids : []
    const names = ids
      .map((rid) => rolesById.get(Number(rid)))
      .filter((r): r is Role => Boolean(r))
      .filter((r) => r.mention_tag !== 'everyone')
      .sort((a, b) => Number(b.id) - Number(a.id))
      .map((r) => r.name)
    if (names.length) return names.join(', ')
    if (m.role && m.role !== 'member') return m.role
    return 'member'
  }

  async function loadAll() {
    setLoading(true)
    setError(null)
    const [settingsRes, rolesRes, membersRes, roomsRes] = await Promise.all([
      fetch(`/api/v1/room/${roomId}/settings`, {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null),
      fetch(`/api/v1/room/${roomId}/roles`, {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null),
      fetch(`/api/v1/room/${roomId}/members`, {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null),
      fetch('/api/v1/rooms', {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null),
    ])

    if (!settingsRes?.ok) {
      setError('Failed to load server settings')
      setLoading(false)
      return
    }

    const settingsPayload = await settingsRes.json().catch(() => null)
    const nextSettings: RoomSettingsPayload = settingsPayload ?? null
    setSettings(nextSettings)
    setNameDraft(String(nextSettings?.name || ''))
    setDescriptionDraft(String(nextSettings?.description || ''))
    setIsPublicDraft(Boolean(nextSettings?.is_public))

    if (rolesRes?.ok) {
      const p = await rolesRes.json().catch(() => null)
      const list: Role[] = Array.isArray(p?.roles) ? p.roles : []
      list.sort((a, b) => {
        const ae = a.mention_tag === 'everyone'
        const be = b.mention_tag === 'everyone'
        if (ae && !be) return 1
        if (!ae && be) return -1
        const aa = a.mention_tag === 'admin'
        const ba = b.mention_tag === 'admin'
        if (aa && !ba) return -1
        if (!aa && ba) return 1
        return Number(b.id) - Number(a.id)
      })
      setRoles(list)
      const nameMap: Record<number, string> = {}
      const everyoneMap: Record<number, boolean> = {}
      const mentionersMap: Record<number, number[]> = {}
      const permissionMap: Record<number, PermissionKey[]> = {}
      for (const r of list) {
        nameMap[r.id] = r.name
        everyoneMap[r.id] = Boolean(r.can_be_mentioned_by_everyone)
        mentionersMap[r.id] = Array.isArray(r.allowed_source_role_ids) ? r.allowed_source_role_ids : []
        permissionMap[r.id] = Array.isArray(r.permissions) ? r.permissions : []
      }
      setRoleNameDrafts(nameMap)
      setRoleMentionEveryoneDrafts(everyoneMap)
      setRoleMentionersDrafts(mentionersMap)
      setRolePermissionDrafts(permissionMap)
    } else {
      setRoles([])
    }

    if (membersRes?.ok) {
      const p = await membersRes.json().catch(() => null)
      const list: Member[] = Array.isArray(p?.members) ? p.members : []
      setMembers(list)
      const memberMap: Record<number, number[]> = {}
      for (const m of list) {
        memberMap[m.id] = Array.isArray(m.role_ids) ? m.role_ids : []
      }
      setMemberRoleDrafts(memberMap)
    } else {
      setMembers([])
    }

    if (roomsRes?.ok) {
      const p = await roomsRes.json().catch(() => null)
      const allRooms = Array.isArray(p?.rooms) ? p.rooms : []
      const room = allRooms.find((r: any) => Number(r?.id) === Number(roomId))
      const nextChannels: ChannelSummary[] = Array.isArray(room?.channels)
        ? room.channels.map((c: any) => ({
          id: Number(c?.id),
          name: String(c?.name || ''),
          writer_role_ids: Array.isArray(c?.writer_role_ids)
            ? c.writer_role_ids.map((x: any) => Number(x)).filter((x: number) => Number.isFinite(x) && x > 0)
            : [],
        }))
        : []
      setChannels(nextChannels)
      const channelMap: Record<number, number[]> = {}
      for (const c of nextChannels) {
        channelMap[c.id] = Array.isArray(c.writer_role_ids) ? c.writer_role_ids : []
      }
      setChannelWriterRoleDrafts(channelMap)
    } else {
      setChannels([])
      setChannelWriterRoleDrafts({})
    }

    setLoading(false)
  }

  useEffect(() => {
    if (!open) return
    void loadAll()
  }, [open, roomId])

  async function saveOverview() {
    if (!canManageServer) return
    setSaving(true)
    setError(null)
    setOk(null)
    const res = await fetch(`/api/v1/room/${roomId}/settings`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        name: nameDraft.trim(),
        description: descriptionDraft.trim(),
        is_public: isPublicDraft,
      }),
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? 'Failed to save settings')
      setSaving(false)
      return
    }
    setOk('Server settings updated')
    await loadAll()
    setSaving(false)
  }

  async function uploadRoomAsset(kind: 'avatar' | 'banner', file: File) {
    if (!canManageServer) return
    const form = new FormData()
    form.append(kind, file)
    const endpoint = kind === 'avatar' ? `/api/v1/room/${roomId}/avatar` : `/api/v1/room/${roomId}/banner`
    const res = await fetch(endpoint, {
      method: 'POST',
      credentials: 'include',
      body: form,
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? `Failed to upload ${kind}`)
      return
    }
    setOk(`${kind === 'avatar' ? 'Avatar' : 'Banner'} updated`)
    await loadAll()
  }

  async function deleteBanner() {
    if (!canManageServer) return
    const res = await fetch(`/api/v1/room/${roomId}/banner/delete`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(() => null)
    if (!res?.ok) return
    setOk('Banner removed')
    await loadAll()
  }

  async function deleteAvatar() {
    if (!canManageServer) return
    const res = await fetch(`/room/${roomId}/avatar/delete`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(() => null)
    if (!res?.ok) return
    setOk('Avatar removed')
    await loadAll()
  }

  async function createRole() {
    if (!canManageRoles) return
    const name = newRoleName.trim()
    if (name.length < 2) return
    const res = await fetch(`/api/v1/room/${roomId}/roles`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ name, permissions: [] }),
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? 'Failed to create role')
      return
    }
    setNewRoleName('')
    setOk('Role created')
    await loadAll()
  }

  async function saveRole(roleId: number) {
    if (!canManageRoles) return
    const name = roleNameDrafts[roleId] ?? ''
    const canMentionEveryone = Boolean(roleMentionEveryoneDrafts[roleId])
    const mentioners = roleMentionersDrafts[roleId] ?? []
    const permissions = rolePermissionDrafts[roleId] ?? []

    const res1 = await fetch(`/api/v1/room/${roomId}/roles/${roleId}`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        name,
        can_be_mentioned_by_everyone: canMentionEveryone,
        permissions,
      }),
    }).catch(() => null)
    if (!res1?.ok) {
      const p = await res1?.json().catch(() => null)
      setError(p?.error ?? 'Failed to update role')
      return
    }

    const res2 = await fetch(`/api/v1/room/${roomId}/roles/${roleId}/mentioners`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ source_role_ids: mentioners }),
    }).catch(() => null)
    if (!res2?.ok) {
      const p = await res2?.json().catch(() => null)
      setError(p?.error ?? 'Failed to update mention permissions')
      return
    }

    setOk('Role updated')
    await loadAll()
  }

  async function deleteRole(roleId: number) {
    if (!canManageRoles) return
    const role = rolesById.get(roleId)
    if (!role || role.is_system) return
    if (!window.confirm(`Delete role "${role.name}"?`)) return
    const res = await fetch(`/api/v1/room/${roomId}/roles/${roleId}`, {
      method: 'DELETE',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? 'Failed to delete role')
      return
    }
    setOk('Role deleted')
    await loadAll()
  }

  async function saveMemberRoles(userId: number) {
    if (!canManageRoles) return
    const roleIds = memberRoleDrafts[userId] ?? []
    const res = await fetch(`/api/v1/room/${roomId}/members/${userId}/roles`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ role_ids: roleIds }),
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? 'Failed to update member roles')
      return
    }
    setOk('Member roles updated')
    await loadAll()
  }

  async function saveChannelPermissions(channelId: number) {
    if (!canManageChannels) return
    const writerRoleIds = channelWriterRoleDrafts[channelId] ?? []
    const res = await fetch(`/api/v1/room/${roomId}/channel/${channelId}/permissions`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ writer_role_ids: writerRoleIds }),
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? 'Failed to update channel permissions')
      return
    }
    setOk('Channel permissions updated')
    await loadAll()
  }

  async function runMemberAction(userId: number, action: 'kick' | 'ban' | 'mute' | 'unmute') {
    let endpoint = ''
    let init: RequestInit = {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }

    if (action === 'kick') endpoint = `/admin/user/${userId}/kick_from_room/${roomId}`
    if (action === 'unmute') endpoint = `/admin/user/${userId}/unmute_in_room/${roomId}`
    if (action === 'mute') {
      endpoint = `/admin/user/${userId}/mute_in_room/${roomId}`
      init = {
        ...init,
        headers: {
          ...init.headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ minutes: 60 }),
      }
    }
    if (action === 'ban') {
      endpoint = `/admin/user/${userId}/ban`
      init = {
        ...init,
        headers: {
          ...init.headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ room_id: roomId, reason: 'Banned by moderator', delete_messages: false }),
      }
    }

    const res = await fetch(endpoint, init).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? `Failed to ${action}`)
      return
    }
    setOk(`Member ${action} completed`)
    await loadAll()
  }

  async function deleteServerFromSettings() {
    if (!canDeleteServer || !deleteConfirmChecked) return
    const res = await fetch(`/room/${roomId}/delete`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(() => null)
    if (!res?.ok) {
      const p = await res?.json().catch(() => null)
      setError(p?.error ?? 'Failed to delete server')
      return
    }
    window.location.href = '/'
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" PaperProps={{ sx: { borderRadius: 3, overflow: 'hidden' } }}>
      <DialogTitle sx={{ fontWeight: 900, pb: 1 }}>Server settings</DialogTitle>
      <DialogContent sx={{ pt: 0 }}>
        <Tabs value={tab} onChange={(_e, v) => setTab(v)}>
          <Tab label="Overview" />
          <Tab label="Roles" />
          <Tab label="Members" />
          <Tab label="Channels" />
        </Tabs>

        {error ? <Alert severity="warning" sx={{ mt: 1 }}>{error}</Alert> : null}
        {ok ? <Alert severity="success" sx={{ mt: 1 }}>{ok}</Alert> : null}
        {loading ? <Typography sx={{ mt: 2 }}>Loading...</Typography> : null}

        {!loading ? (
          <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }} useFlexGap>
            {(settings?.permissions?.granted_permissions || []).map((p) => (
              <Chip key={`perm-chip-${p}`} size="small" label={p} variant="outlined" />
            ))}
            {!settings?.permissions?.granted_permissions?.length ? (
              <Typography variant="caption" color="text.secondary">No extra permissions granted.</Typography>
            ) : null}
          </Stack>
        ) : null}

        {tab === 0 && !loading ? (
          <Box sx={{ mt: 2, display: 'grid', gap: 2 }}>
            <Paper elevation={0} sx={{ p: 1.4, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
              <Stack spacing={1.2}>
                <TextField
                  label="Server name"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  disabled={!canManageServer}
                  fullWidth
                />
                <TextField
                  label="Description"
                  value={descriptionDraft}
                  onChange={(e) => setDescriptionDraft(e.target.value)}
                  disabled={!canManageServer}
                  multiline
                  minRows={3}
                  fullWidth
                />
                <FormControlLabel
                  control={(
                    <Checkbox
                      checked={isPublicDraft}
                      onChange={(e) => setIsPublicDraft(e.target.checked)}
                      disabled={!canManageServer}
                    />
                  )}
                  label="Public server (visible in Explore)"
                />
                <Button variant="contained" onClick={() => void saveOverview()} disabled={!canManageServer || saving}>
                  Save overview
                </Button>
              </Stack>
            </Paper>

            <Paper elevation={0} sx={{ p: 1.4, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <Stack spacing={1} sx={{ minWidth: 220 }}>
                  <Typography fontWeight={800}>Avatar</Typography>
                  <Avatar src={settings?.avatar_url ?? undefined} sx={{ width: 88, height: 88 }} />
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" onClick={() => avatarInputRef.current?.click()} disabled={!canManageServer}>
                      Upload
                    </Button>
                    <Button size="small" color="inherit" onClick={() => void deleteAvatar()} disabled={!canManageServer}>
                      Remove
                    </Button>
                  </Stack>
                </Stack>

                <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', md: 'block' } }} />

                <Stack spacing={1} sx={{ flex: 1 }}>
                  <Typography fontWeight={800}>Banner</Typography>
                  <Box
                    sx={{
                      height: 120,
                      borderRadius: 2,
                      border: '1px solid',
                      borderColor: 'divider',
                      bgcolor: 'background.default',
                      backgroundImage: settings?.banner_url ? `url(${settings.banner_url})` : undefined,
                      backgroundSize: 'cover',
                      backgroundPosition: 'center',
                    }}
                  />
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="outlined" onClick={() => bannerInputRef.current?.click()} disabled={!canManageServer}>
                      Upload
                    </Button>
                    <Button size="small" color="inherit" onClick={() => void deleteBanner()} disabled={!canManageServer}>
                      Remove
                    </Button>
                  </Stack>
                </Stack>
              </Stack>

              <input
                ref={avatarInputRef}
                type="file"
                hidden
                accept="image/*,.gif,.webp"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void uploadRoomAsset('avatar', f)
                  if (avatarInputRef.current) avatarInputRef.current.value = ''
                }}
              />
              <input
                ref={bannerInputRef}
                type="file"
                hidden
                accept="image/*,.gif,.webp"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void uploadRoomAsset('banner', f)
                  if (bannerInputRef.current) bannerInputRef.current.value = ''
                }}
              />
            </Paper>

            <Paper elevation={0} sx={{ p: 1.4, border: '1px solid', borderColor: 'error.main', borderRadius: 2 }}>
              <Typography fontWeight={900} color="error.main">Danger zone</Typography>
              <Typography color="text.secondary" sx={{ mt: 0.7, mb: 1.1 }}>
                Delete server permanently. This action cannot be undone.
              </Typography>
              <FormControlLabel
                control={(
                  <Checkbox
                    checked={deleteConfirmChecked}
                    onChange={(e) => setDeleteConfirmChecked(e.target.checked)}
                    disabled={!canDeleteServer}
                  />
                )}
                label="I understand and want to delete this server"
              />
              <Button
                variant="contained"
                color="error"
                onClick={() => void deleteServerFromSettings()}
                disabled={!canDeleteServer || !deleteConfirmChecked}
              >
                Delete server
              </Button>
            </Paper>
          </Box>
        ) : null}

        {tab === 1 && !loading ? (
          <Box sx={{ mt: 2, display: 'grid', gap: 1.2 }}>
            <Paper elevation={0} sx={{ p: 1.2, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                <TextField
                  label="New role"
                  value={newRoleName}
                  onChange={(e) => setNewRoleName(e.target.value)}
                  disabled={!canManageRoles}
                  fullWidth
                />
                <Button variant="contained" onClick={() => void createRole()} disabled={!canManageRoles || newRoleName.trim().length < 2}>
                  Create role
                </Button>
              </Stack>
            </Paper>

            {roles.map((r) => (
              <Paper key={r.id} elevation={0} sx={{ p: 1.2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
                <Stack spacing={1.2}>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                    <TextField
                      label="Role name"
                      value={roleNameDrafts[r.id] ?? r.name}
                      onChange={(e) => setRoleNameDrafts((prev) => ({ ...prev, [r.id]: e.target.value }))}
                      disabled={!canManageRoles || Boolean(r.is_system)}
                      fullWidth
                    />
                    <Chip label={`@${r.mention_tag}`} variant="outlined" />
                    {!r.is_system ? (
                      <Button color="error" variant="outlined" onClick={() => void deleteRole(r.id)} disabled={!canManageRoles}>
                        Delete
                      </Button>
                    ) : null}
                  </Stack>

                  <FormControlLabel
                    control={(
                      <Checkbox
                        checked={Boolean(roleMentionEveryoneDrafts[r.id])}
                        onChange={(e) => setRoleMentionEveryoneDrafts((prev) => ({ ...prev, [r.id]: e.target.checked }))}
                        disabled={!canManageRoles}
                      />
                    )}
                    label="Can be mentioned by everyone"
                  />

                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                    Permissions
                  </Typography>
                  <Box sx={{ display: 'grid', gap: 0.25, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
                    {ROLE_PERMISSION_OPTIONS.map((perm) => {
                      const checked = (rolePermissionDrafts[r.id] ?? []).includes(perm.key)
                      return (
                        <FormControlLabel
                          key={`${r.id}-perm-${perm.key}`}
                          control={(
                            <Checkbox
                              size="small"
                              checked={checked}
                              onChange={(e) => {
                                setRolePermissionDrafts((prev) => {
                                  const current = prev[r.id] ?? []
                                  const next = e.target.checked
                                    ? Array.from(new Set([...current, perm.key]))
                                    : current.filter((x) => x !== perm.key)
                                  return { ...prev, [r.id]: next }
                                })
                              }}
                              disabled={!canManageRoles}
                            />
                          )}
                          label={perm.label}
                        />
                      )
                    })}
                  </Box>

                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                    Which roles can mention @{r.mention_tag}
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {roles.filter((src) => src.id !== r.id).map((src) => {
                      const checked = (roleMentionersDrafts[r.id] ?? []).includes(src.id)
                      return (
                        <FormControlLabel
                          key={`${r.id}-${src.id}`}
                          control={(
                            <Checkbox
                              size="small"
                              checked={checked}
                              onChange={(e) => {
                                setRoleMentionersDrafts((prev) => {
                                  const current = prev[r.id] ?? []
                                  const next = e.target.checked
                                    ? Array.from(new Set([...current, src.id]))
                                    : current.filter((x) => x !== src.id)
                                  return { ...prev, [r.id]: next }
                                })
                              }}
                              disabled={!canManageRoles}
                            />
                          )}
                          label={src.name}
                        />
                      )
                    })}
                  </Stack>

                  <Button variant="contained" onClick={() => void saveRole(r.id)} disabled={!canManageRoles}>
                    Save role
                  </Button>
                </Stack>
              </Paper>
            ))}
            {!roles.length ? <Typography color="text.secondary">No roles</Typography> : null}
          </Box>
        ) : null}

        {tab === 2 && !loading ? (
          <Box sx={{ mt: 2, display: 'grid', gap: 1.2 }}>
            {members.map((m) => (
              <Paper key={m.id} elevation={0} sx={{ p: 1.2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Avatar src={m.avatar_url ?? undefined} sx={{ width: 30, height: 30 }}>
                      {(m.username || '?').slice(0, 2).toUpperCase()}
                    </Avatar>
                    <Typography fontWeight={800} sx={{ flex: 1 }}>
                      {m.username}
                    </Typography>
                    <Chip size="small" label={displayRolesForMember(m)} />
                    {m.muted_until ? <Chip size="small" color="warning" label="muted" /> : null}
                  </Stack>

                  {canManageRoles ? (
                    <>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                        Assign roles
                      </Typography>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        {roles.map((r) => {
                          const checked = (memberRoleDrafts[m.id] ?? []).includes(r.id)
                          return (
                            <FormControlLabel
                              key={`${m.id}-role-${r.id}`}
                              control={(
                                <Checkbox
                                  size="small"
                                  checked={checked}
                                  onChange={(e) => {
                                    setMemberRoleDrafts((prev) => {
                                      const current = prev[m.id] ?? []
                                      const next = e.target.checked
                                        ? Array.from(new Set([...current, r.id]))
                                        : current.filter((x) => x !== r.id)
                                      return { ...prev, [m.id]: next }
                                    })
                                  }}
                                  disabled={r.is_system && r.mention_tag === 'everyone'}
                                />
                              )}
                              label={r.name}
                            />
                          )
                        })}
                      </Stack>
                      <Button variant="contained" onClick={() => void saveMemberRoles(m.id)} disabled={!canManageRoles}>
                        Save member roles
                      </Button>
                    </>
                  ) : null}

                  {canModerateMembers ? (
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {canMuteMembers ? (
                        m.muted_until ? (
                          <Button size="small" variant="outlined" onClick={() => void runMemberAction(m.id, 'unmute')}>
                            Unmute
                          </Button>
                        ) : (
                          <Button size="small" variant="outlined" onClick={() => void runMemberAction(m.id, 'mute')}>
                            Mute 60m
                          </Button>
                        )
                      ) : null}
                      {canKickMembers ? (
                        <Button size="small" variant="outlined" color="warning" onClick={() => void runMemberAction(m.id, 'kick')}>
                          Kick
                        </Button>
                      ) : null}
                      {canBanMembers ? (
                        <Button size="small" variant="outlined" color="error" onClick={() => void runMemberAction(m.id, 'ban')}>
                          Ban
                        </Button>
                      ) : null}
                    </Stack>
                  ) : null}
                </Stack>
              </Paper>
            ))}
            {!members.length ? <Typography color="text.secondary">No members</Typography> : null}
          </Box>
        ) : null}

        {tab === 3 && !loading ? (
          <Box sx={{ mt: 2, display: 'grid', gap: 1.2 }}>
            {!canManageChannels ? (
              <Alert severity="info">You do not have permission to manage channels.</Alert>
            ) : null}
            {channels.map((ch) => (
              <Paper key={`ch-p-${ch.id}`} elevation={0} sx={{ p: 1.2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
                <Stack spacing={1}>
                  <Typography fontWeight={900}>#{ch.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    If no role is selected, everyone can write. If roles are selected, only those roles can write.
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {roles.map((r) => {
                      const checked = (channelWriterRoleDrafts[ch.id] ?? []).includes(r.id)
                      return (
                        <FormControlLabel
                          key={`ch-${ch.id}-role-${r.id}`}
                          control={(
                            <Checkbox
                              size="small"
                              checked={checked}
                              onChange={(e) => {
                                setChannelWriterRoleDrafts((prev) => {
                                  const current = prev[ch.id] ?? []
                                  const next = e.target.checked
                                    ? Array.from(new Set([...current, r.id]))
                                    : current.filter((x) => x !== r.id)
                                  return { ...prev, [ch.id]: next }
                                })
                              }}
                              disabled={!canManageChannels}
                            />
                          )}
                          label={r.name}
                        />
                      )
                    })}
                  </Stack>
                  <Button variant="contained" onClick={() => void saveChannelPermissions(ch.id)} disabled={!canManageChannels}>
                    Save channel access
                  </Button>
                </Stack>
              </Paper>
            ))}
            {!channels.length ? <Typography color="text.secondary">No channels</Typography> : null}
          </Box>
        ) : null}
      </DialogContent>
      <DialogActions sx={{ px: 2.4, pb: 2.2 }}>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  )
}
