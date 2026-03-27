"""FastAPI server for the video-to-essay web app."""

import os
import re
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from workos import WorkOSClient

from . import db

app = FastAPI(title="Video to Essay", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Serve Next.js static export if it exists
STATIC_DIR = Path(__file__).parent.parent.parent / "web" / "out"

YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}"
)

# ---------------------------------------------------------------------------
# WorkOS client (lazy init — env vars may not be set at import time)
# ---------------------------------------------------------------------------

_workos_client: WorkOSClient | None = None


def _get_workos() -> WorkOSClient:
    global _workos_client
    if _workos_client is None:
        api_key = os.environ.get("WORKOS_API_KEY")
        client_id = os.environ.get("WORKOS_CLIENT_ID")
        if not api_key or not client_id:
            raise RuntimeError("WORKOS_API_KEY and WORKOS_CLIENT_ID must be set")
        _workos_client = WorkOSClient(api_key=api_key, client_id=client_id)
    return _workos_client


def _cookie_password() -> str:
    pw = os.environ.get("WORKOS_COOKIE_PASSWORD")
    if not pw:
        raise RuntimeError("WORKOS_COOKIE_PASSWORD must be set (32+ chars)")
    return pw


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    wos_session: str | None = Cookie(None),
) -> dict[str, Any]:
    """FastAPI dependency that validates the WorkOS session cookie.

    Returns the local user dict from our DB. Raises 401 if not authenticated.
    """
    if not wos_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    workos = _get_workos()
    session = workos.user_management.load_sealed_session(
        sealed_session=wos_session,
        cookie_password=_cookie_password(),
    )

    auth_result = session.authenticate()
    if auth_result.authenticated:
        user = db.get_user_by_workos_id(auth_result.user.id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    # Try refreshing
    try:
        refresh_result = session.refresh()
        if not refresh_result.authenticated:
            raise HTTPException(status_code=401, detail="Session expired")
        # After refresh, authenticate again to get user info
        new_session = workos.user_management.load_sealed_session(
            sealed_session=refresh_result.sealed_session,
            cookie_password=_cookie_password(),
        )
        new_auth = new_session.authenticate()
        if not new_auth.authenticated:
            raise HTTPException(status_code=401, detail="Session expired")
        user = db.get_user_by_workos_id(new_auth.user.id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Note: ideally we'd set the refreshed cookie on the response here,
        # but FastAPI dependencies can't modify the response directly.
        # The frontend should handle 401 by redirecting to login.
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.get("/api/auth/login")
async def auth_login() -> RedirectResponse:
    workos = _get_workos()
    redirect_uri = os.environ.get("WORKOS_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    authorization_url = workos.user_management.get_authorization_url(
        provider="authkit",
        redirect_uri=redirect_uri,
    )
    return RedirectResponse(url=authorization_url)


@app.get("/api/auth/callback")
async def auth_callback(code: str) -> RedirectResponse:
    workos = _get_workos()
    try:
        auth_response = workos.user_management.authenticate_with_code(
            code=code,
            session={"seal_session": True, "cookie_password": _cookie_password()},
        )

        # Upsert user in our DB
        workos_user = auth_response.user
        db.upsert_user(email=workos_user.email, workos_user_id=workos_user.id)

        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="wos_session",
            value=auth_response.sealed_session,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return response

    except Exception as e:
        print(f"Auth callback error: {e}")
        return RedirectResponse(url="/login", status_code=302)


@app.get("/api/auth/logout")
async def auth_logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("wos_session")
    return response


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(get_current_user)) -> dict:
    return {"id": user["id"], "email": user["email"]}


# ---------------------------------------------------------------------------
# Health check (no auth)
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Video endpoints
# ---------------------------------------------------------------------------


class VideoCreate(BaseModel):
    url: str


@app.post("/api/videos")
async def create_video(body: VideoCreate, user: dict = Depends(get_current_user)) -> dict:
    if not YOUTUBE_URL_RE.match(body.url):
        raise HTTPException(status_code=422, detail="Invalid YouTube URL")

    # Extract video ID from URL
    video_id_match = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", body.url)
    if not video_id_match:
        raise HTTPException(status_code=422, detail="Could not extract video ID")
    youtube_video_id = video_id_match.group(1)

    video = db.get_or_create_video(
        youtube_video_id=youtube_video_id,
        youtube_url=body.url,
    )
    db.create_delivery(
        video_id=video["id"],
        user_id=user["id"],
        source="one_off",
    )
    return {"id": video["id"]}


@app.get("/api/videos")
async def list_videos(user: dict = Depends(get_current_user)) -> list[dict]:
    videos = db.list_user_videos(user["id"])
    result = []
    for v in videos:
        status = "pending_download"
        if v.get("error"):
            status = "failed"
        elif v.get("processed_at"):
            status = "done"
        elif v.get("downloaded_at"):
            status = "processing"
        result.append({
            "id": v["id"],
            "youtube_video_id": v["youtube_video_id"],
            "youtube_url": v["youtube_url"],
            "video_title": v.get("video_title"),
            "channel_name": v.get("channel_name"),
            "source": v.get("source"),
            "status": status,
            "error": v.get("error"),
            "delivery_sent_at": v.get("delivery_sent_at"),
            "created_at": v["created_at"],
        })
    return result


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str, user: dict = Depends(get_current_user)) -> dict:
    video = db.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    status = "pending_download"
    if video.get("error"):
        status = "failed"
    elif video.get("processed_at"):
        status = "done"
    elif video.get("downloaded_at"):
        status = "processing"

    result: dict[str, Any] = {
        "id": video["id"],
        "youtube_video_id": video["youtube_video_id"],
        "youtube_url": video["youtube_url"],
        "video_title": video.get("video_title"),
        "status": status,
        "error": video.get("error"),
        "created_at": video["created_at"],
    }

    # If processed, try to read essay from local runs dir (S3 integration later)
    if status == "done":
        essay_path = Path("runs") / video["youtube_video_id"] / "05_place_images" / "essay_final.md"
        if essay_path.exists():
            result["essay_md"] = essay_path.read_text()

    return result


# ---------------------------------------------------------------------------
# Channel / subscription endpoints
# ---------------------------------------------------------------------------


class ChannelCreate(BaseModel):
    url: str


@app.post("/api/channels")
async def subscribe_channel(body: ChannelCreate, user: dict = Depends(get_current_user)) -> dict:
    """Subscribe to a YouTube channel. Accepts a channel URL or video URL."""
    # Extract channel ID — for now, require a channel URL with channel_id param or /channel/ path
    # Full extraction (from video URL) will be added later
    channel_id_match = re.search(r"channel/(UC[\w-]{22})", body.url)
    if not channel_id_match:
        # Try ?channel_id= param
        channel_id_match = re.search(r"channel_id=(UC[\w-]{22})", body.url)
    if not channel_id_match:
        raise HTTPException(
            status_code=422,
            detail="Could not extract channel ID. Use a URL like youtube.com/channel/UC...",
        )
    youtube_channel_id = channel_id_match.group(1)

    # Get or create channel (name will be updated by discover worker later)
    channel = db.get_or_create_channel(
        youtube_channel_id=youtube_channel_id,
        name=youtube_channel_id,  # placeholder, discover worker updates
    )

    # Create subscription (unique constraint prevents duplicates)
    try:
        sub_id = db.create_subscription(
            user_id=user["id"],
            channel_id=channel["id"],
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Already subscribed")

    return {
        "subscription_id": sub_id,
        "channel_id": channel["id"],
        "youtube_channel_id": youtube_channel_id,
        "name": channel.get("name", youtube_channel_id),
    }


@app.get("/api/channels")
async def list_channels(user: dict = Depends(get_current_user)) -> list[dict]:
    return db.list_user_subscriptions(user["id"])


@app.delete("/api/subscriptions/{sub_id}")
async def unsubscribe(sub_id: str, user: dict = Depends(get_current_user)) -> dict:
    sub = db.get_subscription(sub_id)
    if not sub or sub["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.deactivate_subscription(sub_id)
    return {"status": "unsubscribed"}


class SubscriptionUpdate(BaseModel):
    poll_interval_hours: int


@app.patch("/api/subscriptions/{sub_id}")
async def update_subscription(
    sub_id: str, body: SubscriptionUpdate, user: dict = Depends(get_current_user)
) -> dict:
    sub = db.get_subscription(sub_id)
    if not sub or sub["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.update_subscription_interval(sub_id, body.poll_interval_hours)
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Static file serving (Next.js export)
# ---------------------------------------------------------------------------


def mount_static() -> None:
    """Mount the Next.js static export if the build directory exists."""
    if not STATIC_DIR.exists():
        return

    next_dir = STATIC_DIR / "_next"
    if next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(next_dir)), name="next-static")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def spa_fallback(request: Request, full_path: str) -> HTMLResponse:
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return HTMLResponse(file_path.read_text())

        html_path = STATIC_DIR / f"{full_path}.html"
        if html_path.is_file():
            return HTMLResponse(html_path.read_text())

        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return HTMLResponse(index_path.read_text())

        raise HTTPException(status_code=404)
