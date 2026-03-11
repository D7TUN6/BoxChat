import { useContext, useEffect, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { Camera, Lock, Save, Settings, User } from 'lucide-react'
import { ThemeModeContext } from '../ui/theme-mode'

type SettingsPayload = {
  username: string
  avatar_url?: string
  bio: string
  privacy_searchable: boolean
  privacy_listable: boolean
  hide_status: boolean
}

export default function SettingsPage() {
  const theme = useContext(ThemeModeContext)
  const [form, setForm] = useState<SettingsPayload>({
    username: '',
    avatar_url: '',
    bio: '',
    privacy_searchable: true,
    privacy_listable: true,
    hide_status: false,
  })
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [avatarPreviewUrl, setAvatarPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!file) {
      setAvatarPreviewUrl(null)
      return
    }
    let url: string | null = null
    try {
      url = URL.createObjectURL(file)
      setAvatarPreviewUrl(url)
    } catch {
      setAvatarPreviewUrl(null)
    }
    return () => {
      if (url) {
        try {
          URL.revokeObjectURL(url)
        } catch {
          // ignore
        }
      }
    }
  }, [file])

  useEffect(() => {
    let active = true
    async function loadSettings() {
      const res = await fetch('/api/v1/user/settings', {
        credentials: 'include',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(() => null)
      if (!res?.ok || !active) return
      const payload = await res.json().catch(() => null)
      if (payload && active) {
        setForm({
          username: payload.username ?? '',
          avatar_url: payload.avatar_url ?? '',
          bio: payload.bio ?? '',
          privacy_searchable: Boolean(payload.privacy_searchable),
          privacy_listable: Boolean(payload.privacy_listable),
          hide_status: Boolean(payload.hide_status),
        })
      }
    }
    void loadSettings()
    return () => {
      active = false
    }
  }, [])

  async function saveProfile() {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      if (file) {
        const data = new FormData()
        data.append('avatar', file)
        const uploadRes = await fetch('/api/v1/user/avatar', {
          method: 'POST',
          body: data,
          credentials: 'include',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
        if (!uploadRes.ok) {
          const payload = await uploadRes.json().catch(() => null)
          throw new Error(payload?.error ?? 'Failed to upload avatar')
        }
      }

      const settingsRes = await fetch('/api/v1/user/settings', {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          username: form.username.trim(),
          bio: form.bio,
          privacy_searchable: form.privacy_searchable,
          privacy_listable: form.privacy_listable,
          hide_status: form.hide_status,
        }),
      })

      if (!settingsRes.ok) {
        const payload = await settingsRes.json().catch(() => null)
        throw new Error(payload?.error ?? 'Failed to save settings')
      }

      setMessage('Settings updated')
      setFile(null)
    } catch (e: any) {
      setError(e?.message ?? 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  async function changePassword() {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const res = await fetch('/user/change_password', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      })
      const payload = await res.json().catch(() => null)
      if (!res.ok) {
        throw new Error(payload?.error ?? 'Failed to change password')
      }
      setMessage(payload?.message ?? 'Password changed')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e: any) {
      setError(e?.message ?? 'Failed to change password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Settings size={22} />
        <Typography variant="h4">Settings</Typography>
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}
      {message ? <Alert severity="success">{message}</Alert> : null}

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 2 }}>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 1.2 }}>
          Appearance
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1.2, flexWrap: 'wrap' }}>
          <Button
            variant={theme.preset === 'boxchat' ? 'contained' : 'outlined'}
            onClick={() => theme.setPreset('boxchat')}
            disabled={saving}
          >
            BoxChat
          </Button>
          <Button
            variant={theme.preset === 'discord' ? 'contained' : 'outlined'}
            onClick={() => theme.setPreset('discord')}
            disabled={saving}
          >
            Discord
          </Button>
          <Button
            variant={theme.preset === 'discord-ash' ? 'contained' : 'outlined'}
            onClick={() => theme.setPreset('discord-ash')}
            disabled={saving}
          >
            Ash
          </Button>
          <Button
            variant={theme.preset === 'discord-midnight' ? 'contained' : 'outlined'}
            onClick={() => theme.setPreset('discord-midnight')}
            disabled={saving}
          >
            Midnight
          </Button>
          <Button
            variant={theme.preset === 'discord-mint' ? 'contained' : 'outlined'}
            onClick={() => theme.setPreset('discord-mint')}
            disabled={saving}
          >
            Mint
          </Button>
        </Stack>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1 }}>
          <Button
            variant={theme.mode === 'dark' ? 'contained' : 'outlined'}
            onClick={() => theme.setMode('dark')}
            disabled={saving}
          >
            Dark
          </Button>
          <Button
            variant={theme.mode === 'light' ? 'contained' : 'outlined'}
            onClick={() => theme.setMode('light')}
            disabled={saving}
          >
            Light
          </Button>
        </Stack>
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center" mb={2}>
          <Avatar src={avatarPreviewUrl || form.avatar_url} sx={{ width: 72, height: 72 }}>
            {form.username.slice(0, 2).toUpperCase()}
          </Avatar>
          <Stack spacing={0.6}>
            <Typography fontWeight={700}>{form.username}</Typography>
            <Button component="label" variant="outlined" size="small" startIcon={<Camera size={16} />}>
              Upload Avatar
              <input
                hidden
                type="file"
                accept="image/*"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Button>
          </Stack>
        </Stack>

        <Stack spacing={1.3}>
          <TextField
            label="Username"
            value={form.username}
            onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
            helperText="3..30 chars, letters/numbers/_/-"
          />
          <TextField
            label="Bio"
            multiline
            minRows={3}
            value={form.bio}
            onChange={(e) => setForm((prev) => ({ ...prev, bio: e.target.value }))}
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.privacy_searchable}
                onChange={(e) => setForm((prev) => ({ ...prev, privacy_searchable: e.target.checked }))}
              />
            }
            label="Allow search discovery"
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.privacy_listable}
                onChange={(e) => setForm((prev) => ({ ...prev, privacy_listable: e.target.checked }))}
              />
            }
            label="Show in user lists"
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.hide_status}
                onChange={(e) => setForm((prev) => ({ ...prev, hide_status: e.target.checked }))}
              />
            }
            label="Hide online status"
          />
          <Box>
            <Button variant="contained" onClick={() => void saveProfile()} disabled={saving} startIcon={<Save size={16} />}>
              Save Profile
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid', borderColor: 'divider', p: 2 }}>
        <Stack direction="row" spacing={1} alignItems="center" mb={1}>
          <Lock size={18} />
          <Typography variant="h6">Change Password</Typography>
        </Stack>
        <Stack spacing={1.2}>
          <TextField
            type="password"
            label="Old Password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
          <TextField
            type="password"
            label="New Password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <TextField
            type="password"
            label="Confirm Password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <Box>
            <Button variant="outlined" onClick={() => void changePassword()} disabled={saving} startIcon={<User size={16} />}>
              Update Password
            </Button>
          </Box>
        </Stack>
      </Paper>
    </Stack>
  )
}
