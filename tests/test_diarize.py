"""Tests 29-32: diarize.py pure functions."""

from video_to_essay.diarize import format_transcript


# -- Test 29: format_transcript — single speaker, groups consecutive ----------

def test_format_transcript_single_speaker():
    segments = [
        {"speaker": 0, "start": 0.0, "text": "Hello everyone."},
        {"speaker": 0, "start": 5.0, "text": "Welcome to the show."},
        {"speaker": 0, "start": 10.0, "text": "Let's begin."},
    ]
    result = format_transcript(segments)
    assert result == "[00:00] Hello everyone. Welcome to the show. Let's begin."


# -- Test 30: format_transcript — multi-speaker with names --------------------

def test_format_transcript_multi_speaker():
    segments = [
        {"speaker": 0, "start": 0.0, "text": "Hello everyone."},
        {"speaker": 1, "start": 30.0, "text": "Thanks for having me."},
    ]
    names = {0: "Alice", 1: "Bob"}
    result = format_transcript(segments, speaker_names=names)
    assert "**Alice** [00:00]" in result
    assert "Hello everyone." in result
    assert "**Bob** [00:30]" in result
    assert "Thanks for having me." in result


# -- Test 31: format_transcript — empty segments ------------------------------

def test_format_transcript_empty():
    assert format_transcript([]) == ""


# -- Test 32: format_transcript — consecutive same-speaker merged -------------

def test_format_transcript_merges_same_speaker():
    segments = [
        {"speaker": 0, "start": 0.0, "text": "First part."},
        {"speaker": 0, "start": 5.0, "text": "Still talking."},
        {"speaker": 1, "start": 30.0, "text": "My turn."},
        {"speaker": 0, "start": 60.0, "text": "Back to me."},
    ]
    names = {0: "Alice", 1: "Bob"}
    result = format_transcript(segments, speaker_names=names)
    blocks = result.split("\n\n")
    assert len(blocks) == 3
    assert "First part. Still talking." in blocks[0]
    assert "**Bob**" in blocks[1]
    assert "**Alice** [01:00]" in blocks[2]
