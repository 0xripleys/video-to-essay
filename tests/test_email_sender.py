"""Tests 33-37: email_sender.py pure functions."""

from video_to_essay.email_sender import (
    _essay_to_html,
    _essay_to_plaintext,
    _insert_scrivi_link,
)


# -- Test 33: _essay_to_html — valid HTML with inline styles -----------------

def test_essay_to_html():
    html = _essay_to_html("# Title\n\nSome paragraph")
    assert html.startswith("<!DOCTYPE html>")
    assert "max-width: 700px" in html
    assert "<h1>" in html


def test_essay_to_html_preserves_base64_images():
    md = "![Alt](data:image/jpeg;base64,abc123)"
    html = _essay_to_html(md)
    assert "data:image/jpeg;base64,abc123" in html


# -- Test 34: _insert_scrivi_link — after Key Takeaways, before --- ----------

def test_insert_scrivi_link_after_takeaways(sample_essay_md):
    result = _insert_scrivi_link(sample_essay_md, "[Read on Scrivi](https://scrivi.ink)")
    # Link should appear before the ---
    link_pos = result.index("[Read on Scrivi]")
    hr_pos = result.index("\n---\n")
    assert link_pos < hr_pos


# -- Test 35: _insert_scrivi_link — fallback after H1 ------------------------

def test_insert_scrivi_link_fallback_after_h1():
    md = "# My Title\n\nNo takeaways here.\n\nMore content."
    result = _insert_scrivi_link(md, "[Link](url)")
    # Link should appear right after the H1 line
    lines = result.splitlines()
    h1_idx = next(i for i, line in enumerate(lines) if line.startswith("# "))
    link_idx = next(i for i, line in enumerate(lines) if "[Link]" in line)
    assert link_idx > h1_idx
    assert link_idx <= h1_idx + 2


def test_insert_scrivi_link_no_h1():
    md = "Just text without any heading."
    result = _insert_scrivi_link(md, "[Link](url)")
    assert result.startswith("[Link](url)")


# -- Test 36: _essay_to_plaintext — base64 images replaced -------------------

def test_essay_to_plaintext_strips_images():
    md = "Text before\n\n![Alt text](data:image/jpeg;base64,abc123def456)\n\nText after"
    result = _essay_to_plaintext(md)
    assert "[Image: Alt text]" in result
    assert "data:image" not in result
    assert "Text before" in result
    assert "Text after" in result


# -- Test 37: _essay_to_plaintext — wrapping behavior ------------------------

def test_essay_to_plaintext_wraps_long_lines():
    long_line = "This is a very long line that should be wrapped. " * 5
    md = f"# Heading Preserved\n\n> Blockquote preserved\n\n{long_line}\n\n"
    result = _essay_to_plaintext(md)

    for line in result.splitlines():
        if line.startswith("#") or line.startswith(">") or not line.strip():
            continue
        assert len(line) <= 80, f"Line too long ({len(line)} chars): {line[:50]}..."

    assert "# Heading Preserved" in result
    assert "> Blockquote preserved" in result
