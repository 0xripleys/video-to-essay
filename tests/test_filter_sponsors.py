"""Tests 7-11: filter_sponsors.py pure functions."""

import pytest

from video_to_essay.filter_sponsors import _parse_mmss, _strip_segments


# -- Test 7: _parse_mmss — valid and invalid inputs --------------------------

@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("05:30", 330),
        ("0:00", 0),
        ("10:05", 605),
        ("1:30", 90),
        ("invalid", None),
        ("", None),
    ],
)
def test_parse_mmss(timestamp: str, expected: int | None):
    assert _parse_mmss(timestamp) == expected


# -- Test 8: _strip_segments — removes paragraphs within time ranges ----------

def test_strip_segments_removes_sponsor(sample_single_speaker_transcript):
    # [02:00] = 120s falls within range (100, 140)
    result = _strip_segments(sample_single_speaker_transcript, [(100, 140)])
    assert "[00:00]" in result
    assert "[02:00]" not in result
    assert "[04:00]" in result
    assert "[06:00]" in result


# -- Test 9: _strip_segments — handles multi-speaker format -------------------

def test_strip_segments_multi_speaker(sample_multi_speaker_transcript):
    # **Bob** [02:00] = 120s falls within range (100, 140)
    result = _strip_segments(sample_multi_speaker_transcript, [(100, 140)])
    assert "Alice" in result
    assert "[02:00]" not in result
    assert "[04:00]" in result


# -- Test 10: _strip_segments — empty ranges returns unchanged ----------------

def test_strip_segments_empty_ranges(sample_single_speaker_transcript):
    result = _strip_segments(sample_single_speaker_transcript, [])
    assert result == sample_single_speaker_transcript


# -- Test 11: _strip_segments — paragraphs without timestamps always kept -----

def test_strip_segments_keeps_no_timestamp():
    transcript = (
        "This paragraph has no timestamp.\n\n"
        "[01:00] This one does and is sponsored.\n\n"
        "Another paragraph without a timestamp."
    )
    result = _strip_segments(transcript, [(0, 120)])
    assert "This paragraph has no timestamp." in result
    assert "Another paragraph without a timestamp." in result
    assert "[01:00]" not in result
