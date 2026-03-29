# Subscription Flow Redesign

## Problem

The current subscription flow requires users to find a YouTube channel URL, leave the app, copy it, paste it, and hope it resolves to the right channel. There's no search, no preview, and no confirmation step.

## Design

### Smart Input Modal

Replace the inline URL input with a button-triggered modal that accepts both search terms and YouTube URLs.

**Flow:** Page → "Add channel" button → Modal (search/paste) → Select result → Confirm in same modal → Subscribe → Modal closes, list refreshes.

### Page States

**Empty state (no subscriptions):**
- Header: just "Subscriptions" title, no subtitle
- Centered message: "You haven't added any channels yet" / "Add a YouTube channel to get started."
- "+ Add channel" button below the message

**With subscriptions:**
- Header: "Subscriptions" title with "+ Add channel" button to the right
- Channel list below

### Add Channel Modal

Opened by the "+ Add channel" button. Two phases in a single modal:

**Phase 1 — Search:**
- Title: "Add channel"
- Subtitle: "Search for a channel or paste a YouTube URL"
- Smart input that auto-detects mode:
  - **URL detected** (contains `youtube.com` or `youtu.be`): resolve channel via existing `/api/channels` resolve logic, skip to Phase 2
  - **Text detected**: debounced search (300ms) via new `GET /api/channels/search?q=...` endpoint, show dropdown with up to 5 results
- Each search result shows: channel thumbnail, name, subscriber count
- Clicking a result advances to Phase 2

**Phase 2 — Confirm:**
- Channel thumbnail (centered, larger)
- Channel name
- Subscriber count
- Channel description (truncated)
- "Back" button (returns to Phase 1 search) and "Subscribe" button

### After Subscribe

- Modal closes
- Input clears
- Channel list refreshes with the new subscription visible

### Backend Changes

**New endpoint: `GET /api/channels/search?q=...`**
- Calls YouTube Data API v3 `search` endpoint (`type=channel`, `maxResults=5`)
- Returns array of: `channelId`, `name`, `thumbnailUrl`, `subscriberCount`, `description`
- Requires YouTube API key (already available in `youtube.ts`)

**Existing endpoint: `POST /api/channels`** — no changes needed.

### Error Handling

- **Already subscribed:** modal shows "You're already subscribed to this channel" instead of Subscribe button
- **Invalid URL:** inline error below input — "Couldn't find a channel at this URL"
- **Search fails / no results:** dropdown shows "No channels found"
- **Network error:** inline error below input
