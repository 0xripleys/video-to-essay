"""Test 38: summarize.py pure functions."""

from video_to_essay.summarize import _strip_takeaways


# -- Test 38: _strip_takeaways — removes Key Takeaways section ---------------

def test_strip_takeaways_removes_section():
    text = (
        "# Title\n\n"
        "## Key Takeaways\n\n"
        "- Point 1\n"
        "- Point 2\n"
        "---\n\n"
        "## Transcript\n\n"
        "Body text here."
    )
    result = _strip_takeaways(text)
    assert "Key Takeaways" not in result
    assert "Body text here." in result
    assert "# Title" in result


def test_strip_takeaways_triple_hash():
    text = (
        "# Title\n\n"
        "### Key Takeaways\n\n"
        "- Point 1\n"
        "- Point 2\n"
        "---\n\n"
        "Rest of essay."
    )
    result = _strip_takeaways(text)
    assert "Key Takeaways" not in result
    assert "Rest of essay." in result


def test_strip_takeaways_no_section():
    text = "# Title\n\nJust a normal essay without takeaways."
    result = _strip_takeaways(text)
    assert result == text
