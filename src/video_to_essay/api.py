"""FastAPI server for the video-to-essay web app."""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from . import db

app = FastAPI(title="Video to Essay", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Next.js static export if it exists
STATIC_DIR = Path(__file__).parent.parent.parent / "web" / "out"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}"
)


class JobCreate(BaseModel):
    url: str
    email: str

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        if not YOUTUBE_URL_RE.match(v):
            raise ValueError("Invalid YouTube URL")
        return v


class JobResponse(BaseModel):
    id: str
    youtube_url: str
    email: str
    status: str
    current_step: str | None
    error: str | None
    video_title: str | None
    created_at: str
    completed_at: str | None


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=dict)
def create_job(body: JobCreate) -> dict:
    job_id = db.create_job(body.url, body.email)
    return {"id": job_id}


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Static file serving (Next.js export)
# ---------------------------------------------------------------------------


def mount_static() -> None:
    """Mount the Next.js static export if the build directory exists.

    Serves static assets from /_next/* directly, and falls back to serving
    the corresponding .html file for any non-API path (SPA-style routing).
    """
    if not STATIC_DIR.exists():
        return

    # Serve _next/* static assets directly
    next_dir = STATIC_DIR / "_next"
    if next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(next_dir)), name="next-static")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def spa_fallback(request: Request, full_path: str) -> HTMLResponse:
        # Try exact file first (e.g. /foo.js)
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return HTMLResponse(file_path.read_text())

        # Try with .html extension (e.g. /status -> status.html)
        html_path = STATIC_DIR / f"{full_path}.html"
        if html_path.is_file():
            return HTMLResponse(html_path.read_text())

        # Fall back to index.html for client-side routing
        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return HTMLResponse(index_path.read_text())

        raise HTTPException(status_code=404)
