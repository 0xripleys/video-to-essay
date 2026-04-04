"""S3 storage helpers: upload/download run artifacts."""

import mimetypes
import os
from functools import lru_cache
from pathlib import Path

import boto3

RUNS_DIR = Path("runs")


@lru_cache(maxsize=1)
def _get_config() -> tuple[str, str]:
    """Return (bucket_name, region). Fails if S3_BUCKET_NAME is not set."""
    bucket = os.environ["S3_BUCKET_NAME"]
    region = os.environ.get("AWS_REGION", "us-east-1")
    return bucket, region


@lru_cache(maxsize=1)
def get_s3_client():
    _, region = _get_config()
    return boto3.client("s3", region_name=region)


def get_public_url(key: str) -> str:
    bucket, region = _get_config()
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def get_presigned_url(key: str, expires_in: int = 604800) -> str:
    """Generate a pre-signed URL for a private S3 object.

    Args:
        key: S3 object key.
        expires_in: URL expiration in seconds (default 7 days).
    """
    client = get_s3_client()
    bucket, _ = _get_config()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def _content_type(path: Path) -> str:
    ct, _ = mimetypes.guess_type(str(path))
    return ct or "application/octet-stream"


def upload_run(video_id: str, step_dirs: list[str] | None = None) -> None:
    """Upload local run artifacts to S3.

    If step_dirs is given, only upload those subdirectories (e.g. ["00_download"]).
    Otherwise upload the entire runs/<video_id>/ tree.
    """
    client = get_s3_client()
    bucket, _ = _get_config()
    base = RUNS_DIR / video_id

    if step_dirs:
        dirs = [base / d for d in step_dirs]
    else:
        dirs = [base]

    for d in dirs:
        if not d.exists():
            continue
        for file_path in d.rglob("*"):
            if not file_path.is_file() or file_path.name.endswith(".part"):
                continue
            key = f"runs/{video_id}/{file_path.relative_to(base)}"
            client.upload_file(
                str(file_path),
                bucket,
                key,
                ExtraArgs={"ContentType": _content_type(file_path)},
            )
    print(f"S3: uploaded runs/{video_id}/ ({step_dirs or 'all'})")


def download_file(video_id: str, relative_path: str) -> bytes:
    """Download a single file from S3 and return its contents."""
    client = get_s3_client()
    bucket, _ = _get_config()
    key = f"runs/{video_id}/{relative_path}"
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def download_run(video_id: str, step_dirs: list[str] | None = None) -> None:
    """Download run artifacts from S3 to local disk."""
    client = get_s3_client()
    bucket, _ = _get_config()
    prefix = f"runs/{video_id}/"

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Filter to requested step_dirs if specified
            rel = key[len(prefix):]  # e.g. "00_download/video.mp4"
            if step_dirs:
                step = rel.split("/")[0]
                if step not in step_dirs:
                    continue

            local_path = RUNS_DIR / video_id / rel
            local_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(local_path))

    print(f"S3: downloaded runs/{video_id}/ ({step_dirs or 'all'})")
