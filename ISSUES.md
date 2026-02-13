# Essay Output Issues

## 1. Ad Reads Are Treated as Real Content

The transcript contains clear sponsor segments (Grayscale, Coinbase) that get passed through to the essay as if they're editorial content. The essay weaves ad copy into its analysis and includes screenshots of ad slides (e.g. Grayscale product pages, Coinbase loan diagrams) as numbered figures alongside legitimate charts.

**Fix:** Add ad/sponsor detection to filter out sponsor reads before essay generation. Common patterns: "this episode is brought to you by", "investing involves risk, including possible loss of principle", repeated sponsor segments with identical copy.

## 2. No Attribution — Speaker Voices Are Erased

Podcast transcripts are multi-speaker conversations where each participant has distinct views and expertise. The essay flattens all speakers into a single anonymous authoritative voice. You can't tell the output came from a conversation, who said what, or what the original format was (show name, date, participants).

**Approach:** Audio diarization (pyannote.audio) to detect speaker boundaries, then LLM to map speaker IDs to names using video metadata (title, description, channel).

**Pipeline addition:**
1. Detect multi-speaker vs single-speaker from video title/description (cheap LLM call or regex patterns like "interview", "podcast", "ft.", "featuring").
2. For multi-speaker: run pyannote diarization on the audio → get `Speaker 0: 0:00-0:45, Speaker 1: 0:45-1:12, ...`
3. Map speaker IDs to real names using video metadata + LLM.
4. Merge diarization output with transcript text → attributed transcript with `**Speaker Name**` before each turn.
5. Pass attributed transcript to essay generation so the essay preserves speaker identity.

**Notes:**
- pyannote runs on CPU (real-time speed, ~2hr for a 2hr podcast) or GPU (~5-10min). Modal.com is a good option for cheap serverless GPU if needed.
- Works well for 2-3 speakers with distinct voices. Degrades with more speakers or overlapping speech.
- Short utterances ("yeah", "right") are hard to attribute.
- Alternative: LLM-only attribution (no new deps, but less accurate for rapid back-and-forth on noisy auto-captions).
- Reference format: Dwarkesh Patel transcripts — bold speaker name before each turn, sections by topic.

## 3. Over-Formalized Tone

Casual, off-the-cuff podcast dialogue gets transformed into stiff academic/research-note prose that distorts the original register. Colloquial phrases get inflated into formal constructions, losing the personality and energy of the source material.

**Fix:** Instruct the model to match the tone of the source. A podcast recap should read like a podcast recap, not a Goldman Sachs white paper.

## 4. AI Embellishment / Hallucinated Analysis

The model inflates brief conversational observations into multi-paragraph structured theses that nobody actually articulated. A 30-second aside becomes a full subsection with a formal heading and polished argument. This adds words but not information — and misrepresents what was actually said.

**Fix:** Instruct the model to stick closely to what was actually said. Don't expand or elaborate beyond the source material. If a topic got 30 seconds of airtime, it should get a sentence or two in the essay, not its own section.
