# Legal Research Notes

Research conducted Feb 2026 on the legality of downloading YouTube videos, transcribing/editing them, and selling as a subscription service.

## Summary

A business that downloads others' YouTube videos, transcribes them, and sells the transcripts is almost certainly illegal without licensing. It violates YouTube's TOS (breach of contract), infringes copyright by creating unauthorized derivative works, and fails fair use on all four factors — especially after the Supreme Court's 2023 Warhol decision.

## Key Legal Issues

### YouTube TOS
- Explicitly prohibits downloading content without permission from YouTube or the content owner
- Prohibits automated scraping/data extraction
- Violations can lead to account suspension, termination, and legal action
- Breach of contract is a separate legal issue from copyright

### Copyright Law (US)
- A transcript is a **derivative work** under 17 U.S.C. Section 106
- Copyright owner holds exclusive rights to prepare derivative works
- Creating and selling transcripts without permission = infringement

### Fair Use Analysis (all four factors weigh against)

| Factor | Analysis |
|--------|----------|
| Purpose & character | Commercial use weighs against |
| Nature of work | Creative content weighs against |
| Amount used | 100% of spoken content weighs heavily against |
| Market effect | Transcript substitutes for original, weighs strongly against |

### Warhol v. Goldsmith (2023) — Key Precedent
- Supreme Court ruled 7-2 that changing medium/style while serving similar commercial purpose is NOT transformative
- Directly undercuts "video-to-text is transformative" argument
- Bar for "transformative use" is now higher than ever

### International
- Berne Convention (181 countries) protects derivative works including translations/adaptations
- EU: more restrictive than US, no broad fair use doctrine
- UK/Canada/Australia: narrower "fair dealing" — commercial transcription wouldn't qualify

## Financial Exposure
- Statutory damages: $750–$30,000 per work infringed
- Willful infringement: up to $150,000 per work
- Criminal prosecution possible (17 U.S.C. Section 506)
- Attorney's fees recoverable by prevailing party
- 100 videos at max willful damages = up to $15M

## Why YouTube Clipping Appears to Work

Clipping channels (podcast clips, reaction videos, etc.) are **tolerated, not legal**.

### Why clippers get away with it:
1. **Creators want clips** — free marketing, drives subscribers to main channel
2. **Content ID monetizes instead of blocking** — creators choose "monetize" so they get ad revenue from clips
3. **Hired clippers** — growing freelance market where creators pay clippers directly

### Why tolerated != legal:
- Creator can revoke tolerance instantly (3 strikes = channel gone)
- No concept of implied license from past tolerance
- Nintendo, music labels, FremantleMedia have all aggressively enforced when they wanted to

### Clipping vs. Full Transcription

| Factor | 60-sec clip | Full transcript |
|--------|------------|-----------------|
| Amount used | ~1% of a 3-hr podcast | 100% of spoken content |
| Market substitution | Low — doesn't replace podcast | High — why watch if you can read? |
| Fair use strength | Moderate (with commentary) | Very weak |
| Enforcement risk | Low (creators benefit) | High (directly competes) |

## Viable Product Directions

### A. Creator Tool (B2B) — "We turn your videos into essays"
- Creator authorizes processing of their own content
- Revenue: creator pays per video or monthly sub
- Legal: completely clean — creator owns and authorizes
- Comps: Castmagic, Descript, Riverside

### B. Reader Platform (B2C marketplace)
- Creators opt in with licensing agreement, get revenue share
- Readers subscribe to read written versions
- Legal: clean with proper licensing
- Comps: Nebula but for text

### C. Personal Tool (prosumer) — RECOMMENDED START
- User processes videos for personal reference/notes/research
- Never published or resold
- Legal: strongest position — personal use, tool itself doesn't infringe
- Comps: Otter.ai, NotebookLM, Whisper wrappers
- Many existing tools do exactly this without legal challenge

## Recommended Strategy

**Start with C, build toward A.**

1. Launch as a personal CLI tool — legally safest, simplest
2. Accept local files only (don't bundle yt-dlp or any downloader)
3. Let the user handle how they obtained the file
4. Add creator-facing features later
5. Eventually build marketplace (B) once supply and demand exist

### Key design decision for legal safety:
- Accept local audio/video files as input
- Do NOT integrate YouTube downloading into the tool itself
- The tool is just "give me a file, I'll make an essay" — completely clean
