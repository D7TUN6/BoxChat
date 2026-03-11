import { Box, Button, IconButton, Paper, Stack, TextField, Tooltip, Typography } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import useMediaQuery from '@mui/material/useMediaQuery'
import { AtSign, CornerUpLeft, Paperclip, SendHorizontal, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import ChatGifPopover from './ChatGifPopover'
import ImagePreviewDialog from './ImagePreviewDialog'

export type MentionCandidate = { type: 'role' | 'user'; value: string }
export type ReplyTo = { id: number; username: string; snippet: string }
export type MentionUser = { id: number; username: string }
export type MentionRole = { mention_tag: string }

export default function ChatComposer({
  channelId,
  placeholder,
  onSendText,
  sendingFile,
  fileInputRef,
  onSendFile,
  mentionUsers,
  mentionRoles,
  currentUserId,
  replyTo,
  onClearReply,
  onPickGif,
  disabled,
}: {
  channelId: number | null
  placeholder: string
  onSendText: (text: string) => Promise<boolean>
  sendingFile: boolean
  fileInputRef: RefObject<HTMLInputElement | null>
  onSendFile: (file: File, caption: string) => Promise<boolean>
  mentionUsers: MentionUser[]
  mentionRoles: MentionRole[]
  currentUserId?: number | null
  replyTo: ReplyTo | null
  onClearReply: () => void
  onPickGif: (url: string) => void
  disabled?: boolean
}) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const compactPlaceholder = isMobile ? 'Message' : placeholder
  const [input, setInput] = useState('')
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionStart, setMentionStart] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pendingPreviewUrl, setPendingPreviewUrl] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  function clearPendingFile() {
    setPendingFile(null)
    setPendingPreviewUrl((prev) => {
      if (prev) {
        try {
          URL.revokeObjectURL(prev)
        } catch {
          // ignore
        }
      }
      return null
    })
    setPreviewOpen(false)
    try {
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    setInput('')
    setMentionQuery('')
    setMentionStart(null)
    clearPendingFile()
  }, [channelId])

  useEffect(() => {
    return () => {
      if (pendingPreviewUrl) {
        try {
          URL.revokeObjectURL(pendingPreviewUrl)
        } catch {
          // ignore
        }
      }
    }
  }, [pendingPreviewUrl])

  const mentionCandidates = useMemo<MentionCandidate[]>(() => {
    if (mentionStart == null) return []
    const q = mentionQuery.toLowerCase()
    const roleItems = (mentionRoles || [])
      .filter((r) => !q || String(r.mention_tag || '').toLowerCase().startsWith(q))
      .map((r) => ({ type: 'role' as const, value: String(r.mention_tag || '') }))
      .filter((x) => x.value)
    const userItems = (mentionUsers || [])
      .filter((m) => Number(m.id) !== Number(currentUserId || 0))
      .filter((m) => !q || String(m.username || '').toLowerCase().startsWith(q))
      .map((m) => ({ type: 'user' as const, value: String(m.username || '') }))
      .filter((x) => x.value)
    return [...roleItems, ...userItems].slice(0, 10)
  }, [mentionStart, mentionQuery, mentionRoles, mentionUsers, currentUserId])

  function trackMention(value: string, caret: number) {
    const left = value.slice(0, caret)
    const match = left.match(/(?:^|\s)@([a-zA-Z0-9_-]*)$/)
    if (!match) {
      setMentionStart(null)
      setMentionQuery('')
      return
    }
    const q = match[1] ?? ''
    setMentionQuery(q)
    setMentionStart(caret - q.length - 1)
  }

  function applyMention(mentionValue: string) {
    if (mentionStart === null) return
    const start = mentionStart
    const end = mentionStart + 1 + mentionQuery.length
    const before = input.slice(0, start)
    const after = input.slice(end)
    const insert = `@${mentionValue} `
    const next = `${before}${insert}${after}`
    const nextCaret = (before + insert).length
    setInput(next)
    setMentionQuery('')
    setMentionStart(null)
    window.requestAnimationFrame(() => {
      try {
        const el = inputRef.current
        if (!el) return
        el.focus()
        el.setSelectionRange(nextCaret, nextCaret)
      } catch {
        // ignore
      }
    })
  }

  async function sendNow() {
    if (pendingFile) {
      const ok = await onSendFile(pendingFile, input.trim())
      if (!ok) return
      clearPendingFile()
      setInput('')
      setMentionQuery('')
      setMentionStart(null)
      return
    }

    const text = input.trim()
    if (!text) return
    const ok = await onSendText(text)
    if (!ok) return
    setInput('')
    setMentionQuery('')
    setMentionStart(null)
  }

  return (
    <Box
      sx={{
        borderTop: '1px solid',
        borderColor: 'divider',
        px: { xs: 1, md: 2.2 },
        py: { xs: 0.9, md: 1.2 },
        minHeight: { xs: 68, md: 84 },
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        position: 'relative',
        bgcolor: 'background.paper',
      }}
    >
      {mentionCandidates.length > 0 ? (
        <Paper
          elevation={8}
          sx={{
            position: 'absolute',
            left: { xs: 10, md: 24 },
            right: { xs: 10, md: 24 },
            bottom: pendingFile ? { xs: 146, md: 164 } : { xs: 68, md: 76 },
            zIndex: 20,
            border: '1px solid',
            borderColor: 'divider',
            maxHeight: 220,
            overflowY: 'auto',
          }}
        >
          <Stack>
            {mentionCandidates.map((c) => (
              <Button key={`${c.type}-${c.value}`} color="inherit" sx={{ justifyContent: 'flex-start' }} onClick={() => applyMention(c.value)} startIcon={<AtSign size={14} />}>
                @{c.value}
              </Button>
            ))}
          </Stack>
        </Paper>
      ) : null}

      {replyTo ? (
        <Paper elevation={0} sx={{ mb: 1, p: 1, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <CornerUpLeft size={16} />
            <Typography variant="caption" color="text.secondary" noWrap>
              Replying to <b>{replyTo.username}</b>: {replyTo.snippet}
            </Typography>
            <Box sx={{ flex: 1 }} />
            <IconButton size="small" onClick={onClearReply}>
              <X size={14} />
            </IconButton>
          </Stack>
        </Paper>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (!f) return
          setPendingFile(f)
          setPendingPreviewUrl((prev) => {
            if (prev) {
              try {
                URL.revokeObjectURL(prev)
              } catch {
                // ignore
              }
            }
            if (String(f.type || '').startsWith('image/')) {
              try {
                return URL.createObjectURL(f)
              } catch {
                return null
              }
            }
            return null
          })
          setPreviewOpen(false)
          try {
            if (fileInputRef.current) fileInputRef.current.value = ''
          } catch {
            // ignore
          }
        }}
      />

      {pendingFile ? (
        <Paper elevation={0} sx={{ mb: 1, p: 1, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
            {pendingPreviewUrl ? (
              <Box
                component="img"
                src={pendingPreviewUrl}
                alt={pendingFile.name}
                draggable={false}
                onClick={() => setPreviewOpen(true)}
                sx={{
                  width: 54,
                  height: 54,
                  borderRadius: 1.5,
                  objectFit: 'cover',
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'background.paper',
                }}
              />
            ) : (
              <Box
                sx={{
                  width: 54,
                  height: 54,
                  borderRadius: 1.5,
                  border: '1px solid',
                  borderColor: 'divider',
                  bgcolor: 'background.paper',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 900,
                }}
              >
                FILE
              </Box>
            )}

            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography sx={{ fontWeight: 900 }} noWrap>
                {pendingFile.name}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {pendingFile.type || 'application/octet-stream'} · {(pendingFile.size / (1024 * 1024)).toFixed(2)} MB
              </Typography>
            </Box>

            <Tooltip title="Remove attachment">
              <IconButton size="small" onClick={clearPendingFile}>
                <X size={16} />
              </IconButton>
            </Tooltip>
          </Stack>

          <ImagePreviewDialog
            open={previewOpen}
            src={pendingPreviewUrl}
            title={pendingFile.name}
            onClose={() => setPreviewOpen(false)}
          />
        </Paper>
      ) : null}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'auto minmax(0, 1fr) auto auto',
          alignItems: 'center',
          gap: { xs: 0.2, md: 1 },
          px: { xs: 0.8, md: 1 },
          py: { xs: 0.35, md: 0.7 },
          borderRadius: { xs: 999, md: 2 },
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          maxWidth: '100%',
          overflow: 'visible',
        }}
      >
        <Tooltip title="Attach file">
          <span>
            <IconButton
              size="small"
              onClick={() => fileInputRef.current?.click()}
              disabled={!channelId || sendingFile || Boolean(disabled)}
              sx={{ width: { xs: 34, md: 40 }, height: { xs: 34, md: 40 } }}
            >
              <Paperclip size={18} />
            </IconButton>
          </span>
        </Tooltip>

        <TextField
          variant="standard"
          value={input}
          onChange={(e) => {
            const value = e.target.value
            setInput(value)
            const caret = e.target.selectionStart ?? value.length
            trackMention(value, caret)
          }}
          placeholder={compactPlaceholder}
          multiline
          maxRows={6}
          inputRef={(el) => {
            inputRef.current = el
          }}
          InputProps={{
            disableUnderline: true,
            sx: { minWidth: 0 },
          }}
          sx={{
            minWidth: 0,
            width: '100%',
            '& .MuiInputBase-root': { fontSize: { xs: 16, md: 15 } },
            '& .MuiInputBase-input': {
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            },
            '& .MuiInputBase-input::placeholder': { opacity: 0.9, fontSize: { xs: 15, md: 15 } },
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void sendNow()
            }
          }}
        />

        <ChatGifPopover
          disabled={!channelId}
          onPick={(url) => {
            onPickGif(url)
          }}
        />

        <Tooltip title="Send">
          <span>
            <IconButton
              size="small"
              onClick={() => void sendNow()}
              disabled={!channelId || Boolean(disabled) || sendingFile || (!pendingFile && !input.trim())}
              sx={{
                width: { xs: 34, md: 40 },
                height: { xs: 34, md: 40 },
                flexShrink: 0,
                bgcolor: 'transparent',
                color: (t) => (t.palette.mode === 'dark' ? '#ffffff' : '#4e5058'),
                opacity: pendingFile || input.trim() ? 1 : 0.45,
              }}
            >
              <SendHorizontal size={18} />
            </IconButton>
          </span>
        </Tooltip>
      </Box>
    </Box>
  )
}
