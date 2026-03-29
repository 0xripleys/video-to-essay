# Unsubscribe from Channels — Design Spec

## Goal

Add the ability to unsubscribe from channels directly on the home page, via a channels sidebar displayed alongside the video list.

## Layout Changes

- Widen the dashboard container from `max-w-2xl` (672px) to `max-w-4xl` (896px)
- Split the content area into a 2:1 flex layout:
  - **Left (flex-2):** Video list — unchanged from current implementation
  - **Right (flex-1):** Channels sidebar — new

The "Home" heading and "+ New" dropdown remain at the top, spanning full width.

## Channels Sidebar

### Content

Each subscribed channel is displayed as a compact row:
- Circular channel thumbnail (from `thumbnail_url`)
- Channel name
- × button to unsubscribe

### Section header

"Channels" label — uppercase, muted color, matching the existing design language.

### Empty state

When the user has no subscriptions: "No channels yet" with subtext encouraging them to subscribe via the + New dropdown.

## Unsubscribe Flow

1. User clicks × on a channel row
2. A confirm dialog appears: "Unsubscribe from {channel name}?"
   - Two buttons: "Cancel" (secondary) and "Unsubscribe" (red/destructive)
3. On confirm:
   - Call `DELETE /api/subscriptions/{subId}`
   - Remove the channel from the sidebar
   - Refetch the video list (videos from that channel may no longer appear)
4. On cancel: dismiss the dialog, no action

The confirm dialog should be a lightweight centered modal consistent with the existing modal patterns in the app (ConvertVideoModal, AddChannelModal).

## Data Fetching

- Add a `fetchChannels()` function that calls `GET /api/channels`
- Fetch channels on mount alongside the existing `fetchVideos()`
- After a successful unsubscribe, refetch both channels and videos

The `GET /api/channels` endpoint already returns: `id` (subscription ID), `channel_id`, `youtube_channel_id`, `channel_name`, `thumbnail_url`, `description`, `active`, `created_at`.

## Backend

No backend changes needed. The following endpoints already exist:
- `GET /api/channels` — lists active subscriptions with channel details
- `DELETE /api/subscriptions/[subId]` — deactivates subscription (soft delete)

## Files Modified

- `web/app/components/Dashboard.tsx` — add channels sidebar, widen container, add channel fetching, add unsubscribe with confirmation

## Out of Scope

- Editing subscription settings (poll interval)
- Resubscribing to previously unsubscribed channels from this UI
- Filtering videos by channel
