# Essay Output Issues

## 1. Ad Reads Are Treated as Real Content

The transcript contains clear sponsor segments (Grayscale, Coinbase) that get passed through to the essay as if they're editorial content. The essay weaves ad copy into its analysis and includes screenshots of ad slides (e.g. Grayscale product pages, Coinbase loan diagrams) as numbered figures alongside legitimate charts.

**Fix:** Add ad/sponsor detection to filter out sponsor reads before essay generation. Common patterns: "this episode is brought to you by", "investing involves risk, including possible loss of principle", repeated sponsor segments with identical copy.

## 2. No Attribution — Speaker Voices Are Erased

Podcast transcripts are multi-speaker conversations where each participant has distinct views and expertise. The essay flattens all speakers into a single anonymous authoritative voice. You can't tell the output came from a conversation, who said what, or what the original format was (show name, date, participants).

**Fix:** Preserve speaker identity in the essay. At minimum, note it's a roundtable and list participants. Ideally, attribute key claims and opinions to the person who made them.

## 3. Over-Formalized Tone

Casual, off-the-cuff podcast dialogue gets transformed into stiff academic/research-note prose that distorts the original register. Colloquial phrases get inflated into formal constructions, losing the personality and energy of the source material.

**Fix:** Instruct the model to match the tone of the source. A podcast recap should read like a podcast recap, not a Goldman Sachs white paper.

## 4. AI Embellishment / Hallucinated Analysis

The model inflates brief conversational observations into multi-paragraph structured theses that nobody actually articulated. A 30-second aside becomes a full subsection with a formal heading and polished argument. This adds words but not information — and misrepresents what was actually said.

**Fix:** Instruct the model to stick closely to what was actually said. Don't expand or elaborate beyond the source material. If a topic got 30 seconds of airtime, it should get a sentence or two in the essay, not its own section.
