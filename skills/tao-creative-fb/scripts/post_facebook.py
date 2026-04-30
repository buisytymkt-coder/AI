#!/usr/bin/env python3
"""Post image + caption to Facebook Page via Graph API /{page-id}/photos.

Behavior:
- DRY_RUN=true: do not call Facebook API, only print/save preview.
- DRY_RUN=false: publish for real.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = ROOT / "outputs" / "previews"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post photo + caption to Facebook Page")
    parser.add_argument("--image-url", required=True, help="Public image URL to post via Facebook /photos endpoint")
    parser.add_argument("--caption", default="", help="Caption text")
    parser.add_argument("--caption-file", default="", help="Read caption text from local .txt file")
    parser.add_argument("--published", choices=["true", "false"], default="true")
    parser.add_argument("--dry-run", default=None, help="Override DRY_RUN env: true/false")
    return parser.parse_args()


def str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_caption_text(caption: str, caption_file: str) -> str:
    if caption_file:
        path = Path(caption_file)
        if not path.exists():
            raise RuntimeError(f"Caption file not found: {caption_file}")
        return path.read_text(encoding="utf-8").strip()
    return caption.strip()


def save_preview(payload: dict[str, Any], response_data: dict[str, Any] | None, status: str) -> Path:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = PREVIEW_DIR / f"fb_post_{ts}_{status}.json"
    body = {
        "status": status,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "request_payload": payload,
        "response": response_data,
    }
    out.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    load_dotenv()
    args = parse_args()

    page_id = os.getenv("FB_PAGE_ID", "").strip()
    page_token = os.getenv("FB_PAGE_TOKEN", "").strip()

    dry_run_env = str_to_bool(os.getenv("DRY_RUN"), default=False)
    dry_run_cli = str_to_bool(args.dry_run) if args.dry_run is not None else None
    dry_run = dry_run_env if dry_run_cli is None else dry_run_cli

    if not dry_run:
        if not page_id:
            print("[post_facebook] Missing FB_PAGE_ID in environment.", file=sys.stderr)
            return 1
        if not page_token:
            print("[post_facebook] Missing FB_PAGE_TOKEN in environment.", file=sys.stderr)
            return 1

    try:
        caption_text = get_caption_text(args.caption, args.caption_file)
    except Exception as exc:  # noqa: BLE001
        print(f"[post_facebook] {exc}", file=sys.stderr)
        return 1

    if not args.image_url.strip():
        print("[post_facebook] --image-url is required.", file=sys.stderr)
        return 1

    payload = {
        "url": args.image_url.strip(),
        "caption": caption_text,
        "published": args.published,
    }

    if dry_run:
        preview_file = save_preview(payload=payload, response_data=None, status="dry_run")
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "message": "DRY_RUN enabled. Facebook not called.",
                    "preview_file": str(preview_file),
                    "payload": payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    endpoint = f"https://graph.facebook.com/v23.0/{page_id}/photos"
    payload_with_token = {**payload, "access_token": page_token}

    try:
        response = requests.post(endpoint, data=payload_with_token, timeout=30)
    except requests.RequestException as exc:
        print(f"[post_facebook] Network error calling Facebook API: {exc}", file=sys.stderr)
        return 1

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if not response.ok:
        preview_file = save_preview(payload=payload, response_data=data, status="error")
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Facebook API request failed",
                    "status_code": response.status_code,
                    "response": data,
                    "preview_file": str(preview_file),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    preview_file = save_preview(payload=payload, response_data=data, status="posted")
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "status_code": response.status_code,
                "response": data,
                "preview_file": str(preview_file),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
