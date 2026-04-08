"""Tests 1-6: transcriber.py pure functions."""

import pytest

from video_to_essay.transcriber import (
    extract_video_id,
    _extract_speakers,
    _is_multi_speaker,
    _timestamp_instructions,
)


# -- Test 1: extract_video_id — standard URLs --------------------------------

@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=abc_DEF-123", "abc_DEF-123"),
    ],
)
def test_extract_video_id_standard(url: str, expected: str):
    assert extract_video_id(url) == expected


# -- Test 2: extract_video_id — rejects invalid URLs -------------------------

@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "https://example.com",
        "abc",
        "",
        "https://youtube.com/channel/UCxyz",
    ],
)
def test_extract_video_id_invalid(url: str):
    with pytest.raises(ValueError):
        extract_video_id(url)


# -- Test 3: _is_multi_speaker — True for speaker markers --------------------

def test_is_multi_speaker_true(sample_multi_speaker_transcript):
    assert _is_multi_speaker(sample_multi_speaker_transcript) is True


# -- Test 4: _is_multi_speaker — False for single-speaker --------------------

def test_is_multi_speaker_false(sample_single_speaker_transcript):
    assert _is_multi_speaker(sample_single_speaker_transcript) is False


# -- Test 5: _extract_speakers — unique names, insertion order ----------------

def test_extract_speakers_unique_ordered():
    transcript = (
        "**Alice** [00:00]\nHello\n\n"
        "**Bob** [01:00]\nHi\n\n"
        "**Alice** [02:00]\nSo anyway\n\n"
        "**Charlie** [03:00]\nThanks"
    )
    assert _extract_speakers(transcript) == ["Alice", "Bob", "Charlie"]


# -- Test 6: _timestamp_instructions — YouTube link format --------------------

def test_timestamp_instructions():
    result = _timestamp_instructions("abc12345678")
    assert "https://youtube.com/watch?v=abc12345678" in result
    assert "&t=330s" in result
    assert "05:30" in result
