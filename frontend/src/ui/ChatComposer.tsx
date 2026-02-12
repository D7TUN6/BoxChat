import { Box, Button, IconButton, Paper, Stack, TextField, Tooltip, Typography } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import useMediaQuery from '@mui/material/useMediaQuery'
import { AtSign, CornerUpLeft, Paperclip, SendHorizontal, X } from 'lucide-react'
import type { RefObject } from 'react'
import ChatGifPopover from './ChatGifPopover'

export type MentionCandidate = { type: 'role' | 'user'; value: string }
export type ReplyTo = { id: number; username: string; snippet: string }

export default function ChatComposer({
  channelId,
  input,
  setInput,
  placeholder,
  onSend,
  sendingFile,
  fileInputRef,
  onPickFile,
  mentionCandidates,
  applyMention,
  onTrackMention,
  replyTo,
  onClearReply,
  onPickGif,
}: {
  channelId: number | null
  input: string
  setInput: (v: string) => void
  placeholder: string
  onSend: () => void
  sendingFile: boolean
  fileInputRef: RefObject<HTMLInputElement | null>
  onPickFile: (f: File) => void
  mentionCandidates: MentionCandidate[]
  applyMention: (value: string) => void
  onTrackMention?: (value: string, caret: number) => void
  replyTo: ReplyTo | null
  onClearReply: () => void
  onPickGif: (url: string) => void
}) {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const compactPlaceholder = isMobile ? 'Message' : placeholder

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
            bottom: { xs: 68, md: 76 },
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
          if (f) onPickFile(f)
        }}
      />

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
            <IconButton size="small" onClick={() => fileInputRef.current?.click()} disabled={!channelId || sendingFile} sx={{ width: { xs: 34, md: 40 }, height: { xs: 34, md: 40 } }}>
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
            if (onTrackMention) {
              onTrackMention(value, e.target.selectionStart ?? value.length)
            }
          }}
          placeholder={compactPlaceholder}
          multiline
          maxRows={6}
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
              onSend()
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
              onClick={onSend}
              disabled={!channelId || !input.trim()}
              sx={{
                width: { xs: 34, md: 40 },
                height: { xs: 34, md: 40 },
                flexShrink: 0,
                bgcolor: 'transparent',
                color: (t) => (t.palette.mode === 'dark' ? '#ffffff' : '#4e5058'),
                opacity: input.trim() ? 1 : 0.45,
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
