# Landing Page Design

## Goal

Add a public landing page that explains what Surat does and funnels visitors to sign in. Single viewport, no scrolling. Replaces the bare login page for unauthenticated users.

## Layout

Left-aligned hero with before/after visual. Three sections stacked vertically:

### 1. Nav bar

- Left: "Surat" text logo (links to `/`)
- Right: "Sign in" text link (links to `/api/auth/login`)
- No background color, just a subtle bottom border. Matches the stone palette.

### 2. Hero section (flex row)

**Left side (text):**
- Headline: "YouTube videos, as illustrated essays" (or similar)
- Subtitle: one sentence explaining the product — paste a link, get an essay with images, delivered to inbox
- CTA button: "Get started" linking to `/api/auth/login`. Dark stone background (`bg-stone-900`), white text, rounded.

**Right side (before/after visual):**
- Two panels side by side with an arrow between them
- Left panel ("Video"): video thumbnail placeholder with play button, a few skeleton text lines below
- Right panel ("Essay"): title, skeleton text, an image placeholder, a "Figure 1" italic caption, more skeleton text
- This is a static illustration, not interactive. Built with HTML/CSS, no images needed.

### 3. Feature row (3 cards)

Three cards in a horizontal row below the hero:
- **AI essays** — "Transcribed and rewritten by Claude"
- **Key frames** — "Important visuals extracted and placed automatically"
- **Inbox delivery** — "Subscribe to channels, get essays for every new video"

Each card: small icon (plain unicode or simple SVG), bold label, one-line description. Light background (`bg-stone-50` or `bg-white` with border).

## Routing and Auth Check

Current state:
- `/` renders the Dashboard component, which calls `/api/videos` on mount. Unauthenticated users get 401 -> redirected to `/login` by `api.ts`.
- `/login` is a standalone page with a sign-in button.

New behavior:
- `/` becomes a conditional route. `page.tsx` checks auth status by calling `/api/auth/me`.
  - Authenticated: render the Dashboard (current behavior)
  - Not authenticated: render the Landing page
- `/login` redirects to `/` (or is removed). The landing page absorbs its purpose since it has the sign-in CTA.
- `AppShell` currently hides the sidebar on `/login`. Update it to also hide the sidebar when the user is not authenticated (landing page visible at `/`).

Auth check approach:
- `page.tsx` calls `/api/auth/me` on mount. Three states: `loading`, `authenticated`, `unauthenticated`.
- Loading: show nothing (or a minimal centered spinner)
- Authenticated: render `<Dashboard />`
- Unauthenticated: render `<Landing />`

This avoids a flash of the wrong page. The `/api/auth/me` call is fast since it just validates the cookie.

## Components

Two new components, one modified:

### `web/app/components/Landing.tsx` (new)
The full landing page: nav, hero with before/after, feature row. Self-contained, no API calls. All links point to `/api/auth/login`.

### `web/app/page.tsx` (modified)
Currently exports `Dashboard` directly. Change to:
- Call `/api/auth/me` on mount
- Render `<Landing />` or `<Dashboard />` based on auth state
- Extract the existing dashboard code into `web/app/components/Dashboard.tsx` to keep `page.tsx` clean.

### `web/app/components/Dashboard.tsx` (new)
Move existing `page.tsx` dashboard code here, no logic changes.

### `web/app/components/AppShell.tsx` (modified)
Currently checks `pathname === "/login"` to hide sidebar. Change to check auth state instead:
- Call `/api/auth/me` on mount
- If not authenticated, hide the sidebar regardless of route
- If authenticated, show the sidebar (except maybe on `/login` for backwards compat, but `/login` will redirect anyway)

### `web/app/login/page.tsx` (modified)
Redirect to `/` since the landing page now handles unauthenticated users. A simple `useEffect` with `router.push("/")`, or just render a `<Landing />`.

## Styling

Matches existing app palette:
- `stone-900` for primary text and CTA button
- `stone-500` / `stone-400` for secondary text
- `stone-200` for borders
- `stone-50` / white for backgrounds
- Tailwind utility classes, consistent with all existing pages

## Out of Scope

- No analytics or tracking
- No animated transitions or scroll effects
- No real essay screenshots (static HTML/CSS mockup only)
- No A/B testing of copy
- No mobile-specific responsive design (can be a follow-up)
