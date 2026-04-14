import { test } from "node:test";
import assert from "node:assert/strict";
import { extractVideoId, extractPlaylistId, YOUTUBE_URL_RE } from "./youtube.ts";

const VID = "CmwyBcuoMIY";

test("extractVideoId: standard watch URL", () => {
  assert.equal(extractVideoId(`https://www.youtube.com/watch?v=${VID}`), VID);
});

test("extractVideoId: youtu.be short URL", () => {
  assert.equal(extractVideoId(`https://youtu.be/${VID}`), VID);
});

test("extractVideoId: /live/ URL", () => {
  assert.equal(extractVideoId(`https://www.youtube.com/live/${VID}`), VID);
});

test("extractVideoId: /shorts/ URL", () => {
  assert.equal(extractVideoId(`https://www.youtube.com/shorts/${VID}`), VID);
});

test("extractVideoId: /embed/ URL", () => {
  assert.equal(extractVideoId(`https://www.youtube.com/embed/${VID}`), VID);
});

test("extractVideoId: m.youtube.com mobile URL", () => {
  assert.equal(extractVideoId(`https://m.youtube.com/watch?v=${VID}`), VID);
});

test("extractVideoId: watch URL with extra query params before v=", () => {
  assert.equal(
    extractVideoId(`https://www.youtube.com/watch?feature=share&v=${VID}`),
    VID,
  );
});

test("extractVideoId: watch URL with extra query params after v=", () => {
  assert.equal(
    extractVideoId(`https://www.youtube.com/watch?v=${VID}&t=30s`),
    VID,
  );
});

test("extractVideoId: /live/ URL with query params", () => {
  assert.equal(
    extractVideoId(`https://www.youtube.com/live/${VID}?si=abc123`),
    VID,
  );
});

test("extractVideoId: returns null for garbage input", () => {
  assert.equal(extractVideoId("not a url"), null);
  assert.equal(extractVideoId(""), null);
});

test("extractVideoId: does not match 10-char IDs", () => {
  assert.equal(extractVideoId("https://youtu.be/shortid123"), null);
});

// extractVideoId is intentionally permissive: it finds an 11-char id after a known marker
// regardless of host or surrounding path. Host validation is done by YOUTUBE_URL_RE at the API boundary.
test("extractVideoId: permissive — matches on any host (host gate is YOUTUBE_URL_RE)", () => {
  assert.equal(extractVideoId("https://example.com/watch?v=CmwyBcuoMIY"), VID);
});

test("extractVideoId: permissive — matches first 11 chars after marker", () => {
  assert.equal(extractVideoId("https://youtu.be/toolongid12345"), "toolongid12");
});

test("YOUTUBE_URL_RE: accepts standard watch URL", () => {
  assert.ok(YOUTUBE_URL_RE.test(`https://www.youtube.com/watch?v=${VID}`));
});

test("YOUTUBE_URL_RE: accepts youtu.be short URL", () => {
  assert.ok(YOUTUBE_URL_RE.test(`https://youtu.be/${VID}`));
});

test("YOUTUBE_URL_RE: accepts /live/ URL (the bug fix)", () => {
  assert.ok(YOUTUBE_URL_RE.test(`https://www.youtube.com/live/${VID}`));
});

test("YOUTUBE_URL_RE: accepts /shorts/ URL", () => {
  assert.ok(YOUTUBE_URL_RE.test(`https://www.youtube.com/shorts/${VID}`));
});

test("YOUTUBE_URL_RE: accepts /embed/ URL", () => {
  assert.ok(YOUTUBE_URL_RE.test(`https://www.youtube.com/embed/${VID}`));
});

test("YOUTUBE_URL_RE: accepts http://", () => {
  assert.ok(YOUTUBE_URL_RE.test(`http://youtube.com/watch?v=${VID}`));
});

test("YOUTUBE_URL_RE: accepts m.youtube.com", () => {
  assert.ok(YOUTUBE_URL_RE.test(`https://m.youtube.com/watch?v=${VID}`));
});

test("YOUTUBE_URL_RE: accepts watch URL with params before v=", () => {
  assert.ok(
    YOUTUBE_URL_RE.test(`https://www.youtube.com/watch?feature=share&v=${VID}`),
  );
});

test("YOUTUBE_URL_RE: rejects non-YouTube host", () => {
  assert.equal(
    YOUTUBE_URL_RE.test(`https://evil.com/watch?v=${VID}`),
    false,
  );
});

test("YOUTUBE_URL_RE: rejects YouTube homepage", () => {
  assert.equal(YOUTUBE_URL_RE.test("https://www.youtube.com/"), false);
});

test("YOUTUBE_URL_RE: rejects garbage", () => {
  assert.equal(YOUTUBE_URL_RE.test("not a url"), false);
  assert.equal(YOUTUBE_URL_RE.test(""), false);
});

test("extractPlaylistId: still works (regression)", () => {
  assert.equal(
    extractPlaylistId("https://www.youtube.com/playlist?list=PLabc123"),
    "PLabc123",
  );
  assert.equal(
    extractPlaylistId(`https://www.youtube.com/watch?v=${VID}&list=PLxyz`),
    "PLxyz",
  );
  assert.equal(extractPlaylistId("https://example.com"), null);
});
