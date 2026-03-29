# Dashboard Redesign — Design Spec

## Goal

Restructure the authenticated app experience from a single list page into a sidebar-navigated app with distinct Feed and Channels views. The current dashboard feels like a page, not a product — this redesign gives it the structure of a daily-use tool.

This spec supersedes the earlier `2026-03-29-unsubscribe-channels-design.md`.

## App Shell — Sidebar Navigation

Replace the current top nav bar (`Surat ... Sign out`) with a persistent left sidebar.

### Sidebar contents

- **Top:** "Surat" branding
- **Nav items:**
  - "Feed" — the video list (default active view)
  - "Channels" — channel management, with a count badge showing number of active subscriptions
- **Bottom:** User profile row (avatar placeholder + name), "Sign out" link or action

### Layout

- Sidebar is fixed-width (~200px), light background (`bg-stone-50`), right border
- Main content area fills the remaining width
- The sidebar is always visible (no collapse/hamburger for now)

### Routing

Client-side state toggle within `AppShell.tsx` (Feed vs Channels), not separate Next.js routes. Both views render in the same main content area. This keeps the single-page feel and avoids full page reloads.

`AppShell.tsx` will manage a `view` state (`"feed" | "channels"`) and render either `Dashboard` or `ChannelsPage` accordingly. The sidebar nav items set this state.

## Feed Page (replaces current Dashboard)

### Layout

- Single column, `max-w-2xl`, centered within the main content area
- "Feed" heading on the left, "+ New" dropdown on the right

### Date-grouped video list

Videos are grouped by date with section headers:

- **"Today"** — videos created today
- **"Yesterday"** — videos created yesterday
- **Formatted date** (e.g., "Mar 25") — for older videos

Grouping logic: compare `created_at` against the current date in the user's local timezone.

### Video rows

Same as current: thumbnail, title, channel name + relative time, status badge. One change:

- **Processing/queued videos** get a subtle warm background (`bg-amber-50`, `border-amber-100`) to visually distinguish them from completed videos.

### Empty state

Same as current: "No videos yet" with hint text.

### "+ New" dropdown

Keeps both options:
- "Convert a video" (opens ConvertVideoModal)
- "Add a channel" (opens AddChannelModal)

Having "Add a channel" in the Feed's dropdown is useful as a shortcut even though the Channels page also has this action.

### Data fetching

Same as current: `GET /api/videos` on mount, poll every 3s while any video is in-progress.

## Channels Page (new)

### Layout

- Single column, `max-w-2xl`, centered within the main content area
- "Channels" heading on the left, "+ Add channel" button on the right

### Channel list

A vertical list of subscribed channels. Each row contains:

- **Channel avatar** — circular thumbnail from `thumbnail_url` (~36px)
- **Channel name** — bold
- **Metadata** — video count + subscription age (e.g., "8 videos · Subscribed 2w ago")
- **"Unsubscribe" button** — secondary style, right-aligned

### Unsubscribe flow

1. User clicks "Unsubscribe" on a channel row
2. Confirm modal appears: "Unsubscribe from {channel name}?" with channel avatar
   - Subtext: "You'll stop receiving new videos from this channel."
   - Two buttons: "Cancel" (secondary) and "Unsubscribe" (red/destructive)
3. On confirm: `DELETE /api/subscriptions/{subId}`, refetch channel list
4. On cancel: dismiss modal

### "+ Add channel" button

Opens the existing `AddChannelModal`. After subscribing, refetch the channel list.

### Video count per channel

The current `GET /api/channels` endpoint does not return video counts. Two options:

- **Option A:** Add a video count to the `listUserSubscriptions` query (a `COUNT` subquery joining videos)
- **Option B:** Fetch video counts client-side from the videos data

Prefer Option A for simplicity. Add a `video_count` field to the `listUserSubscriptions` query in `db.ts`.

### Empty state

"No channels yet" with subtext: "Subscribe to YouTube channels to automatically receive new videos as essays."

### Data fetching

`GET /api/channels` on mount. Refetch after subscribe or unsubscribe.

## Backend Changes

### `listUserSubscriptions` query update (`web/app/lib/db.ts`)

Add a video count subquery:

```sql
SELECT s.*, c.youtube_channel_id, c.name as channel_name, c.thumbnail_url, c.description,
  (SELECT COUNT(*) FROM videos v
   JOIN deliveries d ON d.video_id = v.id AND d.user_id = s.user_id
   WHERE v.channel_id = c.id) as video_count
FROM subscriptions s
JOIN channels c ON c.id = s.channel_id
WHERE s.user_id = $1 AND s.active = TRUE
ORDER BY s.created_at DESC
```

No other backend changes needed. Existing endpoints:
- `GET /api/channels` — lists active subscriptions
- `DELETE /api/subscriptions/[subId]` — deactivates subscription

## Files Changed

- **`AppShell.tsx`** — Replace top nav with sidebar layout, add `view` state and routing between Feed/Channels
- **`Dashboard.tsx`** — Revert to single column (`max-w-2xl`), remove channels sidebar, add date grouping logic, add warm background for processing videos
- **New: `ChannelsPage.tsx`** — Channel list with avatar, name, video count, unsubscribe button + confirm modal
- **`db.ts`** — Update `listUserSubscriptions` to include video count

## Out of Scope

- Collapsible sidebar / mobile responsive sidebar
- Separate Next.js routes (keeping client-side view toggle)
- Channel detail pages
- Filtering Feed by channel
- Editing subscription settings (poll interval)
