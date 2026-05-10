#!/usr/bin/env python
"""Export per-call LLM costs from run artifacts stored in S3."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from video_to_essay import s3
from video_to_essay.llm_cost_export import export_rows_to_csv, rows_from_s3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export runs/**/llm_calls/*.json from S3 to a flat CSV."
    )
    parser.add_argument(
        "--output",
        default="analysis/llm_call_costs.csv",
        help="CSV output path. Default: analysis/llm_call_costs.csv",
    )
    parser.add_argument(
        "--prefix",
        default="runs/",
        help="S3 prefix to scan. Default: runs/",
    )
    parser.add_argument(
        "--bucket",
        default=None,
        help="Override S3 bucket. Defaults to S3_BUCKET_NAME from the environment.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bucket = args.bucket or os.environ.get("S3_BUCKET_NAME")
    if not bucket:
        raise SystemExit("S3_BUCKET_NAME is required in .env or via --bucket")

    client = s3.get_s3_client()
    rows = rows_from_s3(client, bucket, prefix=args.prefix)
    count = export_rows_to_csv(rows, str(output_path))
    print(f"Wrote {count} LLM call rows to {output_path}")


if __name__ == "__main__":
    main()
