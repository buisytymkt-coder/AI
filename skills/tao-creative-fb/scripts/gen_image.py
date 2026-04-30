#!/usr/bin/env python3
"""Generate Facebook creative images via OpenAI GPT Image API.

Supports two modes:
- organic: one image for page content (default quality low)
- ads: one image for ad creative (default quality medium)

Always saves image locally and returns JSON output for downstream pairing.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "outputs" / "images"

VOICE_RULES = (
    "Brand Chăm Chăm: ấm áp, gần gũi, tự nhiên, đáng tin; hướng tới mẹ bỉm và gia đình có trẻ nhỏ. "
    "Phong cách sạch sẽ, đời thường, chân thực, không phô trương."
)

ANGLE_HINTS = {
    "pain point": "Gợi bối cảnh nỗi đau thực tế: lo con bị gió máy, thời tiết thay đổi, mẹ cần giải pháp an tâm.",
    "solution": "Làm rõ cảm giác giải pháp dịu nhẹ, an tâm, tiện dùng mỗi ngày.",
    "social proof": "Thể hiện niềm tin cộng đồng: nhiều mẹ tin dùng, phản hồi tích cực, vibe chân thật.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate image with gpt-image-1")
    parser.add_argument("--mode", choices=["organic", "ads"], required=True)
    parser.add_argument("--title", required=True, help="Creative title/topic")
    parser.add_argument("--angle", required=True, help="Creative angle")
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", choices=["low", "medium", "high"], default=None)
    parser.add_argument("--prompt-extra", default="", help="Extra prompt details")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--mock", action="store_true", help="Skip OpenAI call and generate local placeholder image")
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini", "pollinations", "hf"],
        default=os.getenv("IMAGE_PROVIDER", "openai"),
        help="Image provider. Default reads IMAGE_PROVIDER env.",
    )
    return parser.parse_args()


def build_prompt(mode: str, title: str, angle: str, prompt_extra: str) -> str:
    common = [
        f"Chủ đề: {title}",
        f"Angle: {angle}",
        VOICE_RULES,
        "Ảnh vuông 1:1, ánh sáng tự nhiên, bố cục rõ chủ thể, màu ấm nhẹ.",
        "Không chứa logo thương hiệu khác, không watermark, không chữ sai chính tả.",
    ]

    if mode == "organic":
        common.extend(
            [
                "Mục tiêu: ảnh cho bài đăng Facebook organic, cảm giác thân thiện và tin cậy.",
                "Ưu tiên bối cảnh gia đình, mẹ và bé, chất liệu thiên nhiên, cảm xúc dịu nhẹ.",
            ]
        )
    else:
        common.extend(
            [
                "Mục tiêu: ảnh quảng cáo Facebook, đủ nổi bật để dừng lướt.",
                "Chừa khoảng trống sạch ở 1/3 phía trên hoặc bên phải để đặt text overlay sau này.",
                "Tương phản vừa đủ để giữ sự chú ý nhưng vẫn tự nhiên.",
            ]
        )

    angle_hint = ANGLE_HINTS.get(angle.lower().strip())
    if angle_hint:
        common.append(angle_hint)

    if prompt_extra.strip():
        common.append(f"Yêu cầu thêm: {prompt_extra.strip()}")

    return "\n".join(common)


def call_openai_with_retry(client: Any, prompt: str, size: str, quality: str, retries: int = 1) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size=size,
                quality=quality,
            ).to_dict()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(
                f"[gen_image] OpenAI error (attempt {attempt + 1}/{retries + 1}): {exc}",
                file=sys.stderr,
            )
            if attempt < retries:
                time.sleep(1.5)
    raise RuntimeError(f"OpenAI image generation failed after retry: {last_error}")


def extract_image_bytes(payload: dict[str, Any]) -> bytes:
    data = payload.get("data") or []
    if not data:
        raise RuntimeError("OpenAI response has no image data.")

    first = data[0]
    b64 = first.get("b64_json")
    if not b64:
        raise RuntimeError("OpenAI response missing b64_json.")

    return base64.b64decode(b64)


def call_gemini_image_with_retry(prompt: str, retries: int = 1) -> bytes:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment.")

    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-preview-image-generation")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=body, timeout=60)
            data = resp.json()
            if not resp.ok:
                raise RuntimeError(f"Gemini API failed: {resp.status_code} {data}")
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or {}
                    b64 = inline.get("data")
                    if b64:
                        return base64.b64decode(b64)
            raise RuntimeError("Gemini response has no image bytes.")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(
                f"[gen_image] Gemini error (attempt {attempt + 1}/{retries + 1}): {exc}",
                file=sys.stderr,
            )
            if attempt < retries:
                time.sleep(1.5)
    raise RuntimeError(f"Gemini image generation failed after retry: {last_error}")


def call_pollinations_image(prompt: str) -> bytes:
    encoded = urllib.parse.quote(prompt)
    seed = int(time.time())
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true"
    resp = requests.get(url, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Pollinations failed: {resp.status_code} {resp.text[:200]}")
    return resp.content


def call_hf_image_with_retry(prompt: str, retries: int = 1) -> bytes:
    api_key = os.getenv("HF_API_KEY")
    if not api_key:
        raise RuntimeError("Missing HF_API_KEY in environment.")
    model = os.getenv("HF_MODEL", "black-forest-labs/FLUX.1-schnell")
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"inputs": prompt}

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=120)
            if not resp.ok:
                # HF may return JSON error payload.
                try:
                    err = resp.json()
                except Exception:  # noqa: BLE001
                    err = resp.text[:300]
                raise RuntimeError(f"HF API failed: {resp.status_code} {err}")
            ctype = resp.headers.get("content-type", "")
            if "image" not in ctype and resp.content.startswith(b"{"):
                raise RuntimeError(f"HF returned non-image payload: {resp.text[:300]}")
            return resp.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(
                f"[gen_image] HF error (attempt {attempt + 1}/{retries + 1}): {exc}",
                file=sys.stderr,
            )
            if attempt < retries:
                time.sleep(2)
    raise RuntimeError(f"HF image generation failed after retry: {last_error}")


def main() -> int:
    load_dotenv()
    args = parse_args()

    quality = args.quality or ("low" if args.mode == "organic" else "medium")
    prompt = build_prompt(args.mode, args.title, args.angle, args.prompt_extra)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_mode = args.mode.replace(" ", "-")
    safe_angle = args.angle.lower().strip().replace(" ", "-")
    filename = f"{ts}_{safe_mode}_{safe_angle}.png"
    image_path = out_dir / filename

    provider = args.provider.lower().strip()

    if args.mock:
        # Tiny 1x1 PNG placeholder for local dry tests.
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9s2MvmcAAAAASUVORK5CYII="
        )
    elif provider == "gemini":
        try:
            image_bytes = call_gemini_image_with_retry(prompt=prompt, retries=1)
        except Exception as exc:
            print(f"[gen_image] Gemini failed, fallback to pollinations: {exc}", file=sys.stderr)
            image_bytes = call_pollinations_image(prompt=prompt)
    elif provider == "pollinations":
        image_bytes = call_pollinations_image(prompt=prompt)
    elif provider == "hf":
        image_bytes = call_hf_image_with_retry(prompt=prompt, retries=1)
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[gen_image] Missing OPENAI_API_KEY in environment.", file=sys.stderr)
            return 1
        try:
            from openai import OpenAI
        except ImportError as exc:
            print(f"[gen_image] Missing dependency openai: {exc}", file=sys.stderr)
            return 1
        client = OpenAI(api_key=api_key)
        payload = call_openai_with_retry(
            client=client,
            prompt=prompt,
            size=args.size,
            quality=quality,
            retries=1,
        )
        image_bytes = extract_image_bytes(payload)
    image_path.write_bytes(image_bytes)

    result = {
        "ok": True,
        "provider": provider,
        "mode": args.mode,
        "title": args.title,
        "angle": args.angle,
        "size": args.size,
        "quality": quality,
        "prompt": prompt,
        "image_path": str(image_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
