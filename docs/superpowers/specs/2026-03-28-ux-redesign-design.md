# UX Redesign

## Problem

The current UX has several issues: the landing page gates everything behind auth, the core CTA (convert a video) isn't immediately obvious, the app splits videos and subscriptions across two separate pages, and the sidebar takes up space with only two nav items. Email delivery — a core value prop — isn't mentioned anywhere on the landing page.

## Design

### Landing Page (Unauthenticated)

**Top bar:** Logo ("Surat") on the left, "Sign in" link on the right.

**Hero section (centered):**
- Headline: "Turn YouTube videos into polished transcripts — delivered to your inbox"
- Subtitle: "Paste a link for a one-off, or subscribe to a channel to get every new video automatically."
- URL input + "Convert" button — available without auth

**Example section:**
- Side-by-side: YouTube video card (thumbnail, title, channel, views) on the left, arrow, polished transcript preview (title, text, embedded image) on the right.
- Labels: "Video" and "Transcript" above each side.

### Landing Page Conversion Flow

1. User pastes a URL and clicks Convert.
2. Video resolves: show a preview card (thumbnail, title, channel) below the input.
3. Prompt sign-in: "Sign in to start converting" with auth button.
4. After auth: redirect to the app. The video is already queued/processing in their feed.

### App Screen (Authenticated)

**Remove sidebar entirely.** Replace with a top bar: logo left, "Sign out" right.

**Single page — unified feed:**
- Header: "Home" title with "+ New" button on the right.
- Chronological feed of all videos — both one-off conversions and subscription-sourced videos. Each row shows: video thumbnail, title, channel name, relative timestamp, and status badge (Ready/Processing/Queued/Failed).
- Clicking a "Ready" video opens the reader page.

**"+ New" dropdown:**
Clicking the button shows a lightweight dropdown (not a modal) with two options:
- "Convert a video" — opens a ConvertVideoModal
- "Add a channel" — opens the existing AddChannelModal

**Empty state:**
- "No videos yet" message with "+ New" button below.

### ConvertVideoModal

Same smart input pattern as AddChannelModal:
- Smart input that accepts YouTube URLs or free-text search terms.
- **URL detected** (contains `youtube.com` or `youtu.be`): resolve video metadata, show preview, then confirm.
- **Text detected**: debounced search (300ms) via new `GET /api/videos/search?q=...` endpoint, show dropdown with up to 5 results. Each result shows: video thumbnail, title, channel name, view count.
- Clicking a result shows a confirmation view with video details + "Convert" button.
- After confirming: video is submitted, modal closes, video appears in feed.

### Backend Changes

**New endpoint: `GET /api/videos/search?q=...`**
- Calls YouTube Data API v3 `search` endpoint (`type=video`, `maxResults=5`, `part=snippet`)
- Fetches view counts via `videos` endpoint in a batched request
- Returns array of: `videoId`, `title`, `channelTitle`, `thumbnailUrl`, `viewCount`, `publishedAt`
- Requires YouTube API key (already available)

**New function in `youtube.ts`: `searchVideos(query)`**
- Mirrors the existing `searchChannels()` pattern.

**Existing endpoint: `POST /api/videos`** — no changes needed, already accepts YouTube URLs.

### Components

- **Landing.tsx** — rewrite: hero with URL input, side-by-side example, sign-in-on-convert flow.
- **AppShell.tsx** — remove sidebar for authenticated users, replace with top bar.
- **Sidebar.tsx** — delete.
- **Dashboard.tsx** — rewrite: unified feed, "+ New" dropdown, no inline URL input.
- **ConvertVideoModal.tsx** — new: smart input with video search + URL resolve + confirm.
- **NewDropdown.tsx** — new: lightweight dropdown triggered by "+ New" button.

### Error Handling

- **Video search fails / no results:** dropdown shows "No videos found"
- **Invalid URL:** inline error below input — "Couldn't find a video at this URL"
- **Network error:** inline error below input
- **Landing page convert without auth:** resolve video preview, then prompt sign-in
