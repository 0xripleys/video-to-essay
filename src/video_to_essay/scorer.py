"""
Essay quality scorer — LLM-as-judge evaluation of essay against source transcript.

Each of 5 dimensions is scored in a separate, parallel API call for better
focus and independent scoring. A final call synthesizes the summary.

Dimensions (each 1-10):
- Faithfulness: every claim traceable to transcript
- Proportionality: essay space matches airtime
- Embellishment: no added analysis/conclusions
- Hallucination: no fabricated facts
- Tone: essay sounds like the speaker

TODO: For long videos (3+ hours), chunk transcript/essay into 20-min windows
with 5-min overlap and score each chunk separately. Keep proportionality as a
full-document call (needs global view). Aggregate chunk scores via mean (or min
for hallucination).
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import anthropic

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# ---------------------------------------------------------------------------
# Per-dimension prompts — each focuses on exactly one rubric
# ---------------------------------------------------------------------------

_BASE_PROMPT = """\
You are a strict quality judge comparing an essay against its source transcript.
Score the essay on the single dimension described below. Use the score_dimension tool.

<TRANSCRIPT>
{transcript}
</TRANSCRIPT>

<ESSAY>
{essay}
</ESSAY>

{rubric}

List every violation you find with direct quotes. If there are no violations, the violations list should be empty."""

_RUBRICS: dict[str, str] = {
    "faithfulness": """\
## Faithfulness (1-10)
Can every claim in the essay be traced back to the transcript?
- 1: Majority of claims have no transcript basis
- 4: Several unsupported claims mixed with accurate ones
- 7: Nearly all claims traceable, minor gaps
- 10: Every claim directly supported by transcript""",

    "proportionality": """\
## Proportionality (1-10)
Does the essay allocate space proportionally to how much airtime each topic received?
- 1: Major topics omitted or minor topics dominate
- 4: Noticeable imbalance — some topics over/under-represented
- 7: Mostly proportional with minor deviations
- 10: Essay space mirrors transcript airtime almost exactly

Also provide a topic_analysis listing 3-5 major topics with their approximate share of transcript vs essay.""",

    "embellishment": """\
## Embellishment (1-10)
Does the essay add analysis, conclusions, or interpretive framing not present in the transcript?
- 1: Heavy editorializing, added conclusions, interpretive framing throughout
- 4: Several instances of added analysis or conclusions
- 7: Mostly faithful, rare minor embellishments
- 10: Zero added analysis — purely reports what was said""",

    "hallucination": """\
## Hallucination (1-10)
Does the essay contain fabricated facts, names, numbers, or specifics not in the transcript?
Only flag claims the essay makes that have NO basis in the transcript. If the transcript says something and the essay faithfully reflects it, that is NOT a hallucination — even if you believe the fact is incorrect. Your job is to compare essay against transcript, not to fact-check either document against world knowledge.
- 1: Multiple fabricated specifics (names, numbers, events) with no transcript basis
- 4: A few invented details not found anywhere in the transcript
- 7: At most one minor detail added beyond what the transcript says
- 10: Every specific in the essay can be found in the transcript""",

    "tone": """\
## Tone (1-10)
Does the essay sound like the speaker, or has it been over-formalized?
- 1: Completely different voice — academic/corporate tone replacing casual speech
- 4: Noticeably more formal, speaker's personality mostly lost
- 7: Generally captures the speaker's style with minor formalization
- 10: Reads as if the speaker wrote it themselves""",
}

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_VIOLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "essay_quote": {"type": "string"},
        "transcript_evidence": {"type": "string", "description": "Relevant transcript excerpt, or empty string if no basis exists"},
        "explanation": {"type": "string"},
    },
    "required": ["essay_quote", "transcript_evidence", "explanation"],
}

_DIMENSION_TOOL: dict[str, Any] = {
    "name": "score_dimension",
    "description": "Submit the score for this dimension.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning": {"type": "string", "description": "Work through the evidence step by step before deciding on a score"},
            "violations": {
                "type": "array",
                "items": _VIOLATION_SCHEMA,
                "description": "All violations found. Empty array if none.",
            },
            "score": {"type": "integer", "description": "1-10"},
            "rationale": {"type": "string", "description": "2-3 sentence rationale"},
        },
        "required": ["reasoning", "violations", "score", "rationale"],
    },
}

_PROPORTIONALITY_TOOL: dict[str, Any] = {
    "name": "score_dimension",
    "description": "Submit the score for this dimension.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning": {"type": "string", "description": "Work through the evidence step by step before deciding on a score"},
            "topic_analysis": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "topic": {"type": "string"},
                        "transcript_share": {"type": "string"},
                        "essay_share": {"type": "string"},
                        "assessment": {"type": "string"},
                    },
                    "required": ["topic", "transcript_share", "essay_share", "assessment"],
                },
                "description": "3-5 major topics with transcript vs essay share",
            },
            "violations": {
                "type": "array",
                "items": _VIOLATION_SCHEMA,
                "description": "All violations found. Empty array if none.",
            },
            "score": {"type": "integer", "description": "1-10"},
            "rationale": {"type": "string", "description": "2-3 sentence rationale"},
        },
        "required": ["reasoning", "topic_analysis", "violations", "score", "rationale"],
    },
}

# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------


def _api_call_with_retry(
    client: anthropic.Anthropic,
    max_retries: int = 3,
    **kwargs: Any,
) -> anthropic.types.Message:
    """Make an API call with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt * 15  # 15s, 30s, 60s
            print(f"    Rate limited, retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Unreachable")


def _score_one_dimension(
    client: anthropic.Anthropic,
    transcript: str,
    essay: str,
    dimension: str,
    model: str,
) -> dict[str, Any]:
    """Score a single dimension via one API call."""
    tool = _PROPORTIONALITY_TOOL if dimension == "proportionality" else _DIMENSION_TOOL
    prompt = _BASE_PROMPT.format(
        transcript=transcript,
        essay=essay,
        rubric=_RUBRICS[dimension],
    )

    msg = _api_call_with_retry(
        client,
        model=model,
        max_tokens=4096,
        tools=[tool],
        tool_choice={"type": "tool", "name": "score_dimension"},
        messages=[{"role": "user", "content": prompt}],
    )

    return msg.content[0].input


DIMENSION_NAMES = ["faithfulness", "proportionality", "embellishment", "hallucination", "tone"]


def score_one(
    transcript: str,
    essay: str,
    dimension: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Score a single dimension. Returns the dimension result dict."""
    client = anthropic.Anthropic()
    return _score_one_dimension(client, transcript, essay, dimension, model)


def score_essay(
    transcript: str,
    essay: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Score an essay against its source transcript across 5 quality dimensions.

    Each dimension is scored in a separate parallel API call for independent
    evaluation. Summary is built from individual rationales.

    Returns a dict with overall_score, dimensions, summary, and model.
    """
    client = anthropic.Anthropic()
    dimension_names = ["faithfulness", "proportionality", "embellishment", "hallucination", "tone"]

    # Score all 5 dimensions in parallel
    dimensions: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_score_one_dimension, client, transcript, essay, name, model): name
            for name in dimension_names
        }
        for future in as_completed(futures):
            name = futures[future]
            dimensions[name] = future.result()
            print(f"  {name}: {dimensions[name]['score']}/10")

    scores = [dimensions[name]["score"] for name in dimension_names]
    summary = " ".join(
        f"{name.capitalize()}: {dimensions[name]['rationale']}"
        for name in dimension_names
    )
    return {
        "overall_score": round(sum(scores) / len(scores), 1),
        "dimensions": dimensions,
        "summary": summary,
        "model": model,
    }
