"""Test 41: scorer.py — score_essay return shape."""

from unittest.mock import MagicMock, patch

from video_to_essay.scorer import score_essay


# -- Test 41: score_essay return shape ----------------------------------------

def test_score_essay_return_shape():
    """Mock the Anthropic client and verify score_essay returns correct keys."""
    mock_dimension_result = {
        "reasoning": "The essay is faithful.",
        "violations": [],
        "score": 8,
        "rationale": "Good fidelity to transcript.",
    }

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock()]
    mock_msg.content[0].input = mock_dimension_result

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch("video_to_essay.scorer.anthropic.Anthropic", return_value=mock_client):
        result = score_essay("transcript text", "essay text", model="test-model")

    assert "overall_score" in result
    assert isinstance(result["overall_score"], float)
    assert result["overall_score"] == 8.0

    assert "dimensions" in result
    assert set(result["dimensions"].keys()) == {
        "faithfulness", "proportionality", "embellishment", "hallucination", "tone"
    }

    assert "summary" in result
    assert isinstance(result["summary"], str)

    assert "model" in result
    assert result["model"] == "test-model"
