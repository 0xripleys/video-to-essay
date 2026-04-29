"""scorer.py — score_essay return shape."""

import json
from unittest.mock import MagicMock, patch

from video_to_essay.scorer import score_essay


def test_score_essay_return_shape():
    """Mock llm.complete and verify score_essay returns correct keys."""
    mock_dimension_result = {
        "reasoning": "The essay is faithful.",
        "violations": [],
        "score": 8,
        "rationale": "Good fidelity to transcript.",
    }

    # Build a litellm-shaped ModelResponse: tool_calls[0].function.arguments
    # is a JSON string carrying the structured output.
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.tool_calls = [MagicMock()]
    mock_response.choices[0].message.tool_calls[0].function.arguments = json.dumps(
        mock_dimension_result
    )

    with patch(
        "video_to_essay.scorer.llm.complete", return_value=mock_response
    ):
        result = score_essay("transcript text", "essay text", model="test-model")

    assert "overall_score" in result
    assert isinstance(result["overall_score"], float)
    assert result["overall_score"] == 8.0

    assert "dimensions" in result
    assert set(result["dimensions"].keys()) == {
        "faithfulness", "proportionality", "embellishment", "hallucination", "tone",
    }

    assert "summary" in result
    assert isinstance(result["summary"], str)

    assert "model" in result
    assert result["model"] == "test-model"
