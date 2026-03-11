import { Box, Dialog, DialogContent, IconButton, Stack, Typography } from '@mui/material'
import { X } from 'lucide-react'

export default function ImagePreviewDialog({
  open,
  src,
  title,
  onClose,
}: {
  open: boolean
  src: string | null
  title?: string
  onClose: () => void
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogContent sx={{ p: { xs: 1.2, sm: 2 }, bgcolor: 'background.default' }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <Typography sx={{ fontWeight: 900, minWidth: 0, flex: 1 }} noWrap>
            {title || 'Preview'}
          </Typography>
          <IconButton onClick={onClose} aria-label="Close">
            <X size={18} />
          </IconButton>
        </Stack>
        {src ? (
          <Box
            component="img"
            src={src}
            alt={title || 'preview'}
            draggable={false}
            sx={{
              width: '100%',
              height: 'auto',
              maxHeight: '80vh',
              objectFit: 'contain',
              borderRadius: 2,
              bgcolor: 'background.paper',
            }}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

