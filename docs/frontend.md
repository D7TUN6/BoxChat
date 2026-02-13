**Frontend Overview**

- Stack: Vite, React 19, TypeScript, Material UI (MUI), react-router-dom, socket.io-client.
- Entry: `frontend/src/main.tsx` → `frontend/src/router.tsx` (routes). App shell in `frontend/src/ui/AppLayout.tsx`.

Key pages (SPA routes):
- `/` Dashboard — `DashboardPage.tsx`
- `/explore` — `ExplorePage.tsx`
- `/notifications` — `NotificationsPage.tsx`
- `/login` — `LoginPage.tsx`
- `/register` — `RegisterPage.tsx`
- `/room/:roomId` — `RoomPage.tsx` (main chat view)

Important UI components:
- `ChatComposer.tsx` — message input, attachments, mention handling, slash commands
- `GifPicker.tsx`, `ChatGifPopover.tsx` — GIF picker and sending via Giphy
- `MessageContextMenu.tsx` — edit/delete/forward/reply etc.
- `CustomAudioPlayer.tsx`, `CustomVideoPlayer.tsx` — media playback
- `UserCardPopover.tsx`, `ServerSettingsDialog.tsx`, `notificationsStore.ts`

Reactivity & performance:
- `react-virtuoso` is included for virtualized/long lists (used for messages)
- Socket.IO client manages real-time events (join, send_message, receive_message, presence, etc.)

Integration notes:
- Uses cookie-based auth and fetch calls with `credentials: 'include'` to talk to backend API endpoints (see docs/api.md).
- Router loader `requireAuthLoader` calls `/api/v1/auth/session` to validate session.
- Room UI (`RoomPage.tsx`) handles: channels, members, roles, reactions, replies, mentions, uploading files, GIFs, read markers, and local unread mention storage.

Developer commands (frontend):
```bash
cd frontend
npm install
npm run dev      # start Vite dev server
npm run build    # build production assets
```
