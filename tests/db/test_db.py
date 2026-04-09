"""Tests 44-69: database CRUD, state transitions, queue queries, deliveries."""

import uuid

from video_to_essay import db


# ---------------------------------------------------------------------------
# Helpers — unique IDs to avoid collisions
# ---------------------------------------------------------------------------

def _uniq() -> str:
    return uuid.uuid4().hex[:8]


def make_user() -> str:
    return db.create_user(f"u{_uniq()}@test.com", f"wos_{_uniq()}")


def make_channel(name: str = "Test Channel") -> str:
    return db.create_channel(f"UC_{_uniq()}", name)


def make_video(**kw) -> str:
    return db.create_video(
        f"yt_{_uniq()}", f"https://youtube.com/watch?v={_uniq()}", **kw
    )


# ---------------------------------------------------------------------------
# Basic CRUD — Tests 44-51
# ---------------------------------------------------------------------------


# -- Test 44: init_db is idempotent ------------------------------------------

def test_init_db(pg_container):
    db.init_db()  # second call; should not raise


# -- Test 45: create_user + get_user_by_workos_id roundtrip ------------------

def test_create_user_get_by_workos_id(pg_container):
    wos_id = f"wos_{_uniq()}"
    uid = db.create_user("alice@test.com", wos_id)
    user = db.get_user_by_workos_id(wos_id)
    assert user is not None
    assert user["id"] == uid
    assert user["email"] == "alice@test.com"
    assert user["workos_user_id"] == wos_id
    assert user["created_at"] is not None


# -- Test 46: upsert_user — creates then returns existing --------------------

def test_upsert_user(pg_container):
    wos_id = f"wos_{_uniq()}"
    u1 = db.upsert_user("bob@test.com", wos_id)
    u2 = db.upsert_user("bob@test.com", wos_id)
    assert u1["id"] == u2["id"]
    assert u1["email"] == u2["email"]


# -- Test 47: create_channel + get_channel_by_youtube_id roundtrip -----------

def test_create_channel_get_by_youtube_id(pg_container):
    yt_id = f"UC_{_uniq()}"
    cid = db.create_channel(yt_id, "My Channel")
    ch = db.get_channel_by_youtube_id(yt_id)
    assert ch is not None
    assert ch["id"] == cid
    assert ch["name"] == "My Channel"
    assert ch["youtube_channel_id"] == yt_id


# -- Test 48: get_or_create_channel idempotent -------------------------------

def test_get_or_create_channel(pg_container):
    yt_id = f"UC_{_uniq()}"
    c1 = db.get_or_create_channel(yt_id, "Ch")
    c2 = db.get_or_create_channel(yt_id, "Ch")
    assert c1["id"] == c2["id"]


# -- Test 49: create_video + get_video with all fields -----------------------

def test_create_video_get_video(pg_container):
    cid = make_channel()
    vid = db.create_video(
        f"yt_{_uniq()}",
        "https://youtube.com/watch?v=abc",
        channel_id=cid,
        video_title="My Video",
        matched_playlist_ids=["PL1", "PL2"],
        is_livestream=True,
    )
    v = db.get_video(vid)
    assert v is not None
    assert v["channel_id"] == cid
    assert v["video_title"] == "My Video"
    assert v["matched_playlist_ids"] == ["PL1", "PL2"]
    assert v["is_livestream"] is True
    assert v["downloaded_at"] is None
    assert v["processed_at"] is None
    assert v["error"] is None


# -- Test 50: get_or_create_video idempotent ---------------------------------

def test_get_or_create_video(pg_container):
    yt_id = f"yt_{_uniq()}"
    v1 = db.get_or_create_video(yt_id, "https://youtube.com/watch?v=x")
    v2 = db.get_or_create_video(yt_id, "https://youtube.com/watch?v=x")
    assert v1["id"] == v2["id"]


# -- Test 51: create_subscription + get_subscription roundtrip ---------------

def test_create_subscription_get_subscription(pg_container):
    uid = make_user()
    cid = make_channel()
    sid = db.create_subscription(uid, cid, poll_interval_hours=2, playlist_ids=["PL_a"])
    s = db.get_subscription(sid)
    assert s is not None
    assert s["user_id"] == uid
    assert s["channel_id"] == cid
    assert s["poll_interval_hours"] == 2
    assert s["playlist_ids"] == ["PL_a"]
    assert s["active"] is True


# ---------------------------------------------------------------------------
# State Transitions — Tests 52-55
# ---------------------------------------------------------------------------


# -- Test 52: mark_video_downloaded ------------------------------------------

def test_mark_video_downloaded(pg_container):
    vid = make_video()
    db.mark_video_downloaded(vid, video_title="Updated Title")
    v = db.get_video(vid)
    assert v["downloaded_at"] is not None
    assert v["video_title"] == "Updated Title"

    # Without title — should not overwrite
    vid2 = make_video(video_title="Original")
    db.mark_video_downloaded(vid2)
    v2 = db.get_video(vid2)
    assert v2["downloaded_at"] is not None
    assert v2["video_title"] == "Original"


# -- Test 53: mark_video_processed ------------------------------------------

def test_mark_video_processed(pg_container):
    vid = make_video()
    db.mark_video_processed(vid)
    v = db.get_video(vid)
    assert v["processed_at"] is not None


# -- Test 54: mark_video_failed ---------------------------------------------

def test_mark_video_failed(pg_container):
    vid = make_video()
    db.mark_video_failed(vid, "download error")
    v = db.get_video(vid)
    assert v["error"] == "download error"


# -- Test 55: deactivate_subscription ---------------------------------------

def test_deactivate_subscription(pg_container):
    uid = make_user()
    cid = make_channel()
    sid = db.create_subscription(uid, cid)
    db.deactivate_subscription(sid)
    s = db.get_subscription(sid)
    assert s["active"] is False


# ---------------------------------------------------------------------------
# Queue Queries — Tests 56-59
# ---------------------------------------------------------------------------


# -- Test 56: get_videos_pending_download ------------------------------------

def test_get_videos_pending_download(pg_container):
    vid1 = make_video()
    vid2 = make_video()
    vid3 = make_video()

    db.mark_video_downloaded(vid1)
    db.mark_video_failed(vid2, "error")

    pending = db.get_videos_pending_download()
    pending_ids = [v["id"] for v in pending]
    assert vid3 in pending_ids
    assert vid1 not in pending_ids
    assert vid2 not in pending_ids


# -- Test 57: get_videos_pending_processing ----------------------------------

def test_get_videos_pending_processing(pg_container):
    vid1 = make_video()  # downloaded only
    vid2 = make_video()  # downloaded + processed
    vid3 = make_video()  # not downloaded

    db.mark_video_downloaded(vid1)
    db.mark_video_downloaded(vid2)
    db.mark_video_processed(vid2)

    pending = db.get_videos_pending_processing()
    pending_ids = [v["id"] for v in pending]
    assert vid1 in pending_ids
    assert vid2 not in pending_ids
    assert vid3 not in pending_ids


# -- Test 58: get_channels_due_for_check — respects poll interval ------------

def test_channels_due_for_check(raw_conn):
    uid = make_user()
    cid = make_channel()
    db.create_subscription(uid, cid, poll_interval_hours=1)

    # Channel never checked → should be due
    due = db.get_channels_due_for_check()
    due_ids = [c["id"] for c in due]
    assert cid in due_ids

    # Set last_checked_at to 2 hours ago → still due
    raw_conn.execute(
        "UPDATE channels SET last_checked_at = NOW() - INTERVAL '2 hours' WHERE id = %s",
        (cid,),
    )
    raw_conn.commit()
    due = db.get_channels_due_for_check()
    due_ids = [c["id"] for c in due]
    assert cid in due_ids

    # Set last_checked_at to just now → not due
    raw_conn.execute(
        "UPDATE channels SET last_checked_at = NOW() WHERE id = %s",
        (cid,),
    )
    raw_conn.commit()
    due = db.get_channels_due_for_check()
    due_ids = [c["id"] for c in due]
    assert cid not in due_ids


# -- Test 59: get_channels_due_for_check — no active subs → excluded --------

def test_channels_due_no_active_subs(pg_container):
    uid = make_user()
    cid = make_channel()
    sid = db.create_subscription(uid, cid)
    db.deactivate_subscription(sid)

    due = db.get_channels_due_for_check()
    due_ids = [c["id"] for c in due]
    assert cid not in due_ids


# ---------------------------------------------------------------------------
# Delivery Logic — Tests 60-66
# ---------------------------------------------------------------------------


# -- Test 60: create_delivery — returns ID, then None on duplicate -----------

def test_create_delivery_idempotent(pg_container):
    uid = make_user()
    vid = make_video()
    d1 = db.create_delivery(vid, uid, "one_off")
    d2 = db.create_delivery(vid, uid, "one_off")
    assert isinstance(d1, str)
    assert d2 is None


# -- Test 61: create_subscription_deliveries — basic -------------------------

def test_create_subscription_deliveries(pg_container):
    uid = make_user()
    cid = make_channel()
    db.create_subscription(uid, cid)
    vid = make_video(channel_id=cid)
    db.mark_video_downloaded(vid)
    db.mark_video_processed(vid)

    count = db.create_subscription_deliveries()
    assert count == 1

    pending = db.get_pending_deliveries()
    assert len(pending) == 1
    assert pending[0]["video_id"] == vid


# -- Test 62: create_subscription_deliveries — playlist filter ---------------

def test_sub_deliveries_playlist_filter(pg_container):
    uid = make_user()
    cid = make_channel()
    db.create_subscription(uid, cid, playlist_ids=["PL_a"])

    # Video A: overlapping playlist
    vid_a = make_video(channel_id=cid, matched_playlist_ids=["PL_a", "PL_b"])
    db.mark_video_downloaded(vid_a)
    db.mark_video_processed(vid_a)

    # Video B: non-overlapping playlist
    vid_b = make_video(channel_id=cid, matched_playlist_ids=["PL_c"])
    db.mark_video_downloaded(vid_b)
    db.mark_video_processed(vid_b)

    count = db.create_subscription_deliveries()
    assert count == 1

    pending = db.get_pending_deliveries()
    assert len(pending) == 1
    assert pending[0]["video_id"] == vid_a


# -- Test 63: create_subscription_deliveries — exclude livestreams -----------

def test_sub_deliveries_exclude_livestreams(raw_conn):
    uid = make_user()
    cid = make_channel()
    sid = db.create_subscription(uid, cid)

    # Set exclude_livestreams via raw SQL (not exposed in create_subscription)
    raw_conn.execute(
        "UPDATE subscriptions SET exclude_livestreams = TRUE WHERE id = %s", (sid,)
    )
    raw_conn.commit()

    # Livestream video
    vid_live = make_video(channel_id=cid, is_livestream=True)
    db.mark_video_downloaded(vid_live)
    db.mark_video_processed(vid_live)

    # Normal video
    vid_normal = make_video(channel_id=cid, is_livestream=False)
    db.mark_video_downloaded(vid_normal)
    db.mark_video_processed(vid_normal)

    count = db.create_subscription_deliveries()
    assert count == 1

    pending = db.get_pending_deliveries()
    assert len(pending) == 1
    assert pending[0]["video_id"] == vid_normal


# -- Test 64: create_subscription_deliveries — skips already delivered -------

def test_sub_deliveries_skip_already_delivered(pg_container):
    uid = make_user()
    cid = make_channel()
    db.create_subscription(uid, cid)
    vid = make_video(channel_id=cid)
    db.mark_video_downloaded(vid)
    db.mark_video_processed(vid)

    # Manually create delivery first
    db.create_delivery(vid, uid, "one_off")

    count = db.create_subscription_deliveries()
    assert count == 0


# -- Test 65: get_pending_deliveries ----------------------------------------

def test_get_pending_deliveries(pg_container):
    uid = make_user()
    cid = make_channel()

    # Video 1: processed, delivery unsent → should appear
    vid1 = make_video(channel_id=cid)
    db.mark_video_downloaded(vid1)
    db.mark_video_processed(vid1)
    d1 = db.create_delivery(vid1, uid, "one_off")

    # Video 2: processed, delivery sent → should NOT appear
    vid2 = make_video(channel_id=cid)
    db.mark_video_downloaded(vid2)
    db.mark_video_processed(vid2)
    d2 = db.create_delivery(vid2, uid, "one_off")
    db.mark_delivery_sent(d2)

    # Video 3: NOT processed, delivery created → should NOT appear
    vid3 = make_video(channel_id=cid)
    # Need a different user to avoid UNIQUE(video_id, user_id) conflict on uid
    uid2 = make_user()
    d3 = db.create_delivery(vid3, uid2, "one_off")

    pending = db.get_pending_deliveries()
    pending_ids = [d["id"] for d in pending]
    assert d1 in pending_ids
    assert d2 not in pending_ids
    assert d3 not in pending_ids

    # Verify joined fields
    entry = next(d for d in pending if d["id"] == d1)
    assert "youtube_video_id" in entry
    assert "email" in entry
    assert "channel_name" in entry


# -- Test 66: mark_delivery_sent / mark_delivery_failed ---------------------

def test_mark_delivery_sent_and_failed(pg_container):
    uid = make_user()
    vid1 = make_video()
    vid2 = make_video()
    d1 = db.create_delivery(vid1, uid, "one_off")
    d2 = db.create_delivery(vid2, uid, "one_off")

    db.mark_delivery_sent(d1)
    db.mark_delivery_failed(d2, "smtp error")

    pending = db.get_pending_deliveries()
    pending_ids = [d["id"] for d in pending]
    assert d1 not in pending_ids
    assert d2 not in pending_ids


# ---------------------------------------------------------------------------
# Listing Queries — Tests 67-69
# ---------------------------------------------------------------------------


# -- Test 67: list_user_subscriptions — active only, with channel info -------

def test_list_user_subscriptions(pg_container):
    uid = make_user()
    cid1 = make_channel("Channel A")
    cid2 = make_channel("Channel B")
    sid1 = db.create_subscription(uid, cid1)
    sid2 = db.create_subscription(uid, cid2)
    db.deactivate_subscription(sid2)

    subs = db.list_user_subscriptions(uid)
    assert len(subs) == 1
    assert subs[0]["id"] == sid1
    assert subs[0]["channel_name"] == "Channel A"
    assert "youtube_channel_id" in subs[0]


# -- Test 68: list_user_videos — one-off + subscription, deduped -------------

def test_list_user_videos(pg_container):
    uid = make_user()
    cid = make_channel()

    # Video A: one-off delivery
    vid_a = make_video()
    db.create_delivery(vid_a, uid, "one_off")

    # Video B: subscription video (on subscribed channel)
    db.create_subscription(uid, cid)
    vid_b = make_video(channel_id=cid)

    videos = db.list_user_videos(uid)
    video_ids = [v["id"] for v in videos]
    assert vid_a in video_ids
    assert vid_b in video_ids

    # No duplicates
    assert len(video_ids) == len(set(video_ids))


# -- Test 69: get_channel_subscriptions — active only ------------------------

def test_get_channel_subscriptions(pg_container):
    uid1 = make_user()
    uid2 = make_user()
    cid = make_channel()
    sid1 = db.create_subscription(uid1, cid)
    sid2 = db.create_subscription(uid2, cid)
    db.deactivate_subscription(sid2)

    subs = db.get_channel_subscriptions(cid)
    assert len(subs) == 1
    assert subs[0]["id"] == sid1
