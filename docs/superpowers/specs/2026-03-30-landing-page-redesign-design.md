# Landing Page Redesign: Real Essay Example

## Goal

Replace the placeholder mockup on the landing page with a real essay output to demonstrate product quality. Simplify the hero to a headline + CTA.

## Design

### Hero Section

- Nav bar unchanged (Surat logo left, Sign in right)
- Centered headline: "Turn YouTube videos into polished transcripts — delivered to your inbox"
- Subtitle: "Paste a link for a one-off, or subscribe to a channel to get every new video automatically."
- Single "Get started" button linking to `/api/auth/login`
- Remove: URL input form, video preview card, error handling state, `resolving`/`preview`/`error` state variables

### Essay Example Section

- Replaces the old side-by-side placeholder mockup entirely
- Renders real essay content from the Markets Weekly video (`tdFEbFJ4rbk`)
- Shows first ~3-4 paragraphs + 2-3 images (enough to demonstrate quality)
- Container: max-width ~650px (readable article width), centered
- Images: full width within container, with figure captions
- Gradient fade at bottom: content fades to `stone-50` page background
- No "read more" link — the fade implies more, the CTA above is the action

### Content Strategy

- Essay text + images (base64) are hardcoded as static content in the component
- No runtime fetching, no API dependency
- Source: `runs/tdFEbFJ4rbk/05_place_images/essay_with_images.md`

## What Gets Removed

- URL input form and all associated state (`url`, `error`, `preview`, `resolving`)
- `proxyImageUrl` import (no longer needed)
- Video preview card component
- Side-by-side mockup section (sample video card + arrow + transcript card)
