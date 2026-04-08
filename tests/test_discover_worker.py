"""Tests 39-40: discover_worker.py pure functions."""

import pytest

from video_to_essay.discover_worker import (
    _parse_iso8601_duration,
    _uploads_playlist_id,
)


# -- Test 39: _uploads_playlist_id — UC to UU conversion ---------------------

def test_uploads_playlist_id():
    assert _uploads_playlist_id("UCxyz123abc") == "UUxyz123abc"


def test_uploads_playlist_id_short():
    assert _uploads_playlist_id("UC") == "UU"


# -- Test 40: _parse_iso8601_duration — various formats ----------------------

@pytest.mark.parametrize(
    "duration, expected",
    [
        ("PT1H2M30S", 3750),
        ("PT45S", 45),
        ("PT0S", 0),
        ("", 0),
        ("PT1H", 3600),
        ("PT5M", 300),
        ("PT1H30S", 3630),
        ("P0D", 0),
    ],
)
def test_parse_iso8601_duration(duration: str, expected: int):
    assert _parse_iso8601_duration(duration) == expected
