# Runs Viewer — Design

**Date:** 2026-04-29
**Status:** Approved, ready for implementation planning

## Goal

Build a small, admin-only debugging UI inside the existing Next.js web app that lets a single user (the project owner) inspect every artifact produced by the process worker pipeline for any video, end-to-end. The primary use case is *understanding why an essay turned out the way it did* — what the transcript looked like, which sponsor segments were stripped, which frames Haiku rejected, what the pre- vs post-image essay looked like.

This is a debug/inspection tool, not a user-facing feature. Read-only.

## Non-goals

- Not a generic S3 browser. The pipeline structure is the value-add.
- Not multi-tenant. Single hardcoded admin email.
- Not retroactively re-running steps from the UI. Pure inspection.
- Not surfacing data that isn't already persisted (e.g. pre-dedup frame variants are not on disk and won't be shown).

## Architecture

Two new routes added inside the existing Next.js app at `web/app/runs/`:

- `/runs` — list view (admin landing)
- `/runs/[videoId]` — detail view, tabbed by pipeline step

A shared `web/app/runs/layout.tsx` does the auth gate once for both routes. Server components fetch from Postgres and S3 in parallel; a single client component renders the tabbed UI.

## 1. Routes & access control

Auth gate in `web/app/runs/layout.tsx`:

```ts
const user = await getCurrentUser();
const isDev = !process.env.WORKOS_API_KEY;
if (!isDev && user?.email !== "neerajen.sritharan@gmail.com") notFound();
```

- Dev mode (`WORKOS_API_KEY` unset): wide open, matches the existing dev-mode bypass pattern in `web/app/lib/auth.ts`.
- Production: only `neerajen.sritharan@gmail.com` passes. Anyone else gets a 404 (not 403 — we don't want to advertise the route's existence).

The hardcoded email is a deliberate choice — single-admin tool, no email-allowlist abstraction needed.

## 2. List view (`/runs`)

Server component. Queries the existing `videos` table directly (reusing `web/app/lib/db.ts`) and renders a table.

**Layout:**

```
[Jump to video ID: ____________ ] [Go]

Filter: [All] [Done] [Failed] [Processing]

Title                Channel    Status    Created
─────────────────────────────────────────────────
Some Video Title…    Channel A  done      2d ago
Another Title…       Channel B  failed    3d ago
…
```

**Behavior:**

- 50 most recent videos by `created_at DESC`. Pagination via `?offset=N` query param.
- Filter chips: `?status=done|failed|processing|all` (default `all`).
- Click a row → `/runs/<youtube_video_id>`.
- Jump-to-ID input handles raw IDs (`abc123_XYZ`) and full YouTube URLs (extracts the ID via the same regex `transcriber.extract_video_id` uses on the Python side — port that to TS).
- Status badges color-coded: done = green, failed = red, processing/discovered/downloaded = stone.

## 3. Detail view (`/runs/[videoId]`)

Server component fetches everything in parallel; client component renders tabs.

**Server-side fetch (parallel):**

- DB row: `SELECT * FROM videos WHERE youtube_video_id = $1`
- S3 small artifacts (text/JSON), all via a single `getRunArtifacts()` call:
  - `00_download/metadata.json`
  - `01_transcript/transcript.txt`
  - `01_transcript/speaker_map.json` (optional, multi-speaker only)
  - `02_filter_sponsors/sponsor_segments.json`
  - `03_essay/essay.md`
  - `04_frames/classifications.json`
  - `05_place_images/essay_final.md`
- Listing of `04_frames/kept/` to know which frames survived filtering (used by the Frames gallery to set KEPT/REJECTED status).
- Frame JPGs are NOT fetched server-side. They load directly from public S3 URLs in the browser.

Total page payload ≈ 50–200KB of text. Acceptable for an admin tool.

**Layout:**

```
← Back to runs
[Video Title]                        [done] · 2d ago
youtube.com/watch?v=abc123 ↗ · channel name

[Overview] [Transcript] [Sponsors] [Essay] [Frames] [Final] [Raw files]

  <tab content>
```

Tab state stored in URL hash (`#frames`) for shareable links and reload preservation.

If a step's artifacts are missing (e.g. video still processing, or step failed), the corresponding tab shows a graceful empty state with a hint about which step has not run.

## 4. Per-step views

| Tab | Source files | View |
|-----|------|------|
| **Overview** | `00_download/metadata.json` + DB row | Metadata table: title, channel, duration, description, internal video ID, youtube_video_id, status, created_at, error (if any). |
| **Transcript** | `01_transcript/transcript.txt`, `speaker_map.json` | Plain rendered transcript preserving `[MM:SS]` and `**Speaker**` formatting. Speaker map shown above as a small legend if multi-speaker. |
| **Sponsors** | `01_transcript/transcript.txt` + `02_filter_sponsors/sponsor_segments.json` | Original transcript with paragraphs in sponsor ranges rendered with red strikethrough + light red background. Header lists detected ranges as `MM:SS – MM:SS`. Empty state if `sponsor_segments.json` is `[]`. |
| **Essay** | `03_essay/essay.md` | Rendered markdown using the existing `markdownToHtml` from `web/app/reader/page.tsx` (extract to a shared module). This is the pre-image essay with Key Takeaways. |
| **Frames** | `04_frames/classifications.json` + frame JPGs from S3 | Custom gallery (see below). |
| **Final** | `05_place_images/essay_final.md` | Rendered markdown using the same shared renderer. |
| **Raw files** | All steps | Tree view of the S3 prefix `runs/<videoId>/`. Click a file: JSON pretty-printed, `.txt`/`.md` shown raw, `.jpg`/`.mp3`/`.mp4` embedded. Lazy-loads file content on click via `/api/runs/[videoId]/files`. |

### Frames gallery (custom view)

Grid of frame tiles. Each tile shows:

- Thumbnail (lazy-loaded `<img loading="lazy">` from public S3 URL via `getPublicUrl()`)
- `[MM:SS]` timestamp badge
- Category badge (slide / chart / code / diagram / key_moment / talking_head / transition / advertisement / other)
- Value 1–5 (color-coded: 5 green → 1 red)
- KEPT / REJECTED pill. Source of truth for KEPT status: a frame is KEPT iff its filename appears in `runs/<videoId>/04_frames/kept/`. The server fetches that listing alongside the other artifacts and passes the kept set to the client. For REJECTED frames, the *reason* is derived client-side from the same rules in `extract_frames.extract_and_classify` (purely cosmetic — used to label the badge):
  - `category in {talking_head, transition, advertisement}` → "category filter"
  - `value < 3` → "low value"
  - both → show whichever applied first in the rule chain (category filter takes precedence)
- Truncated description (click tile to expand into a modal showing full description)

**Filter chips at top:**

- `All` / `Kept only` / `Rejected only`
- Category multi-select (chips for each category present in the data)

**Sort:** by timestamp ascending (the only sort that matches the video chronology).

**Note:** `classifications.json` contains only the deduped frames, not all raw samples. Frames collapsed by pHash dedup are not persisted today and are not shown. (Out of scope for this spec.)

### Raw files tab

Server-rendered tree of `runs/<videoId>/` from `ListObjectsV2`. Indented by step:

```
00_download/
  metadata.json          1.2 KB
  video.mp4             45.8 MB
01_transcript/
  audio.mp3             12.3 MB
  diarization.json       8.4 KB
  transcript.txt         5.1 KB
  ...
```

Click a file → fetch contents from `/api/runs/[videoId]/files?path=<relative_path>` and render in a side pane. Server route does the S3 GET.

Render rules:
- `.json` → pretty-printed
- `.txt`, `.md` → preformatted text (no markdown rendering — this is the "raw" tab)
- `.jpg`, `.png` → `<img>` from public S3 URL
- `.mp3` → `<audio controls>`
- `.mp4` → `<video controls>`
- Anything else → "Binary file (X KB)" with a download link

## 5. File layout

```
web/app/
  runs/
    layout.tsx              ← auth gate
    page.tsx                ← list view (server component)
    [videoId]/
      page.tsx              ← detail server component (fetches S3 + DB)
      RunDetail.tsx         ← client component (tabs)
      tabs/
        Overview.tsx
        Transcript.tsx
        Sponsors.tsx
        Essay.tsx
        Frames.tsx
        Final.tsx
        RawFiles.tsx
  lib/
    s3.ts                   ← extended (see below)
    markdown.ts             ← extracted from reader/page.tsx
  api/
    runs/
      [videoId]/
        files/
          route.ts          ← GET tree listing + single-file fetch
```

### `web/app/lib/s3.ts` additions

```ts
export async function getRunArtifact(
  videoId: string,
  relativePath: string,
): Promise<string | null>;

export async function getRunArtifacts(
  videoId: string,
  relativePaths: string[],
): Promise<Record<string, string | null>>;  // path → content

export async function listRunFiles(
  videoId: string,
): Promise<{ key: string; size: number; lastModified: Date }[]>;

export function getPublicUrl(videoId: string, relativePath: string): string;
```

`getPublicUrl` mirrors the Python `s3.get_public_url` so frame images can be loaded directly without proxying.

### `web/app/lib/markdown.ts` (extracted)

The existing `markdownToHtml` function from `web/app/reader/page.tsx` lifted into a shared module. `reader/page.tsx` updates to import from there. No behavior change.

## Data flow summary

```
GET /runs/<videoId>
  └─ runs/[videoId]/page.tsx (server)
       ├─ db.getVideoByYoutubeId(videoId)         ← Postgres
       └─ s3.getRunArtifacts(videoId, [...paths]) ← parallel S3 GETs
       └─ <RunDetail video={…} artifacts={…} />   ← client component

User clicks "Frames" tab
  └─ Frames.tsx renders tiles using classifications.json + getPublicUrl()
  └─ Browser lazy-loads frame JPGs directly from S3

User clicks "Raw files" → clicks a file
  └─ GET /api/runs/<videoId>/files?path=01_transcript/diarization.json
  └─ route.ts fetches from S3, returns content
```

## Error handling

- **Video ID not found in DB:** detail page shows "Video not found" with a Back link.
- **S3 artifact missing:** that tab shows a graceful empty state with the missing path. Other tabs continue to work.
- **Video status is `failed`:** Overview tab prominently shows the `error` field. Other tabs may show empty states.
- **Auth fail in production:** `notFound()` returns 404. No login redirect — this isn't a user-facing route.

## Testing

This is a thin internal admin tool. Manual verification suffices:

- List view loads and shows recent videos
- Filter chips narrow the list correctly
- Jump-to-ID with both raw IDs and full YouTube URLs routes correctly
- Detail view loads for a known-good `done` video
- Each tab renders without crashing
- Sponsors tab shows strikethrough on a video known to have sponsor reads
- Frames gallery filter chips work
- Raw files tree expands and serves individual files
- Auth gate: in dev mode all access works; can be smoke-tested in production with a non-admin account

## Out of scope

- Persisting pre-dedup frames so the gallery can show what got collapsed.
- Diff view between `essay.md` and `essay_final.md`.
- Re-running pipeline steps from the UI.
- Bulk operations across multiple runs.
- Telemetry/analytics on this admin tool.

## Implementation order (suggested)

1. Auth-gated layout + list view + jump-to-ID
2. Detail view scaffold with tabs and parallel S3 fetch
3. Overview / Transcript / Essay / Final tabs (cheap, mostly markdown rendering)
4. Sponsors tab (transcript with highlighted ranges)
5. Frames gallery
6. Raw files tab
