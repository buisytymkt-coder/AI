#!/usr/bin/env python3
"""Generate Facebook captions/ad copy that match Chăm Chăm brand voice.

Modes:
- organic: hook + body + soft CTA
- ads: stronger hook + USP + clear CTA

Outputs JSON for easy pairing with generated images.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "outputs" / "previews"

VOICE_RULES = """
Bạn là content creator cho brand Chăm Chăm.
Tone bắt buộc: ấm áp, gần gũi, tự nhiên, như chị em nói chuyện.
Dùng câu ngắn, rõ ý, viết như nói.
Tránh giọng hàn lâm, sáo rỗng, quá thương mại, phóng đại công dụng.
Đối tượng: mẹ bỉm và gia đình có trẻ nhỏ.
Có thể dùng 1-2 cụm gần gũi như: "chị em ơi", "nói thật là", "chị em nhé" nhưng không lạm dụng.
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate caption/copy with OpenAI")
    parser.add_argument("--mode", choices=["organic", "ads"], required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--angle", required=True)
    parser.add_argument("--usp", default="Tinh dầu tràm Huế thiên nhiên, an tâm cho gia đình có bé nhỏ")
    parser.add_argument("--brand-name", default="Chăm Chăm")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--mock", action="store_true", help="Skip OpenAI call and generate deterministic sample text")
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini"],
        default=os.getenv("TEXT_PROVIDER", "openai"),
        help="Text provider. Default reads TEXT_PROVIDER env.",
    )
    return parser.parse_args()


def build_prompt(args: argparse.Namespace) -> str:
    if args.mode == "organic":
        structure = (
            "Viết 1 caption Facebook organic 80-150 từ bằng tiếng Việt, gồm: "
            "(1) hook gần gũi, (2) body hữu ích thực tế, (3) soft CTA nhẹ nhàng."
        )
        cta_hint = "CTA kiểu mềm: mời inbox, mời để lại từ khóa, hoặc hỏi ý kiến nhẹ nhàng."
    else:
        structure = (
            "Viết 1 ad copy Facebook 80-150 từ bằng tiếng Việt, gồm: "
            "(1) hook mạnh dừng lướt, (2) USP rõ, (3) CTA rõ ràng hành động ngay."
        )
        cta_hint = "CTA kiểu mạnh: inbox ngay, đặt thử hôm nay, nhận tư vấn ngay."

    constraints = [
        "Không dùng claim tuyệt đối kiểu '100%' hoặc phóng đại công dụng.",
        "Không dùng giọng ép mua thô.",
        "Kết thúc bằng CTA đúng mode.",
        "Trả về đúng nội dung caption/copy, không thêm giải thích.",
    ]

    return "\n".join(
        [
            VOICE_RULES,
            structure,
            cta_hint,
            f"Brand: {args.brand_name}",
            f"Chủ đề: {args.title}",
            f"Angle: {args.angle}",
            f"USP tham chiếu: {args.usp}",
            "Ràng buộc:",
            *[f"- {line}" for line in constraints],
        ]
    )


def word_count(text: str) -> int:
    return len([w for w in text.replace("\n", " ").split(" ") if w.strip()])


def call_text_with_retry(client: Any, prompt: str, retries: int = 1) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.responses.create(
                model="gpt-5-mini",
                input=prompt,
                temperature=0.8,
            )
            text = (resp.output_text or "").strip()
            if not text:
                raise RuntimeError("Empty text response")
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(
                f"[gen_caption] OpenAI error (attempt {attempt + 1}/{retries + 1}): {exc}",
                file=sys.stderr,
            )
            if attempt < retries:
                time.sleep(1.5)
    raise RuntimeError(f"OpenAI caption generation failed after retry: {last_error}")


def call_gemini_text_with_retry(prompt: str, retries: int = 1) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment.")
    model = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=body, timeout=45)
            data = resp.json()
            if not resp.ok:
                raise RuntimeError(f"Gemini API failed: {resp.status_code} {data}")
            text = ""
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if part.get("text"):
                        text += part["text"]
            text = text.strip()
            if not text:
                raise RuntimeError("Empty text from Gemini.")
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(
                f"[gen_caption] Gemini error (attempt {attempt + 1}/{retries + 1}): {exc}",
                file=sys.stderr,
            )
            if attempt < retries:
                time.sleep(1.5)
    raise RuntimeError(f"Gemini caption generation failed after retry: {last_error}")


def main() -> int:
    load_dotenv()
    args = parse_args()

    prompt = build_prompt(args)
    provider = args.provider.lower().strip()

    if args.mock:
        if args.mode == "organic":
            text = (
                "Chị em ơi, mấy hôm thời tiết đổi thất thường là nhà có bé nhỏ lại lo ngay ngáy. "
                "Nói thật là chỉ cần chuẩn bị một thói quen chăm bé đều đặn, mẹ sẽ thấy nhẹ đầu hơn nhiều. "
                "Tụi mình ưu tiên cách dùng đơn giản, an toàn, dễ duy trì mỗi ngày để bé thoải mái hơn và mẹ cũng an tâm hơn. "
                "Nếu chị em muốn Trâm gửi cách dùng nhanh theo độ tuổi của bé, cứ để lại chữ TRÀM hoặc inbox nhé."
            )
        else:
            text = (
                "Con vừa trở trời là mẹ cuống cả buổi? Đừng để nỗi lo nhỏ kéo dài thành stress mỗi ngày. "
                "Tinh dầu tràm Huế Chăm Chăm được nhiều mẹ chọn vì mùi dịu, dễ dùng và hợp nhịp chăm bé tại nhà. "
                "Giải pháp gọn nhẹ, tiện mang theo, giúp mẹ chủ động hơn khi thời tiết thay đổi. "
                "Inbox ngay để Trâm tư vấn nhanh cách dùng phù hợp theo độ tuổi bé nhà mình nhé. "
                "Chị em cần, Trâm gửi luôn checklist dùng hằng ngày để đỡ quên."
            )
    else:
        if provider == "gemini":
            try:
                text = call_gemini_text_with_retry(prompt=prompt, retries=1)
            except Exception as exc:
                print(f"[gen_caption] Gemini failed: {exc}", file=sys.stderr)
                return 1
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("[gen_caption] Missing OPENAI_API_KEY in environment.", file=sys.stderr)
                return 1
            try:
                from openai import OpenAI
            except ImportError as exc:
                print(f"[gen_caption] Missing dependency openai: {exc}", file=sys.stderr)
                return 1
            client = OpenAI(api_key=api_key)
            text = call_text_with_retry(client, prompt=prompt, retries=1)
    wc = word_count(text)

    # Keep constraints enforceable for downstream checks.
    if wc < 80 or wc > 150:
        print(
            f"[gen_caption] Warning: word count is {wc}, outside target 80-150.",
            file=sys.stderr,
        )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_mode = args.mode.replace(" ", "-")
    safe_angle = args.angle.lower().strip().replace(" ", "-")

    txt_path = out_dir / f"{ts}_{safe_mode}_{safe_angle}.txt"
    meta_path = out_dir / f"{ts}_{safe_mode}_{safe_angle}.json"

    txt_path.write_text(text + "\n", encoding="utf-8")

    result: dict[str, Any] = {
        "ok": True,
        "provider": provider,
        "mode": args.mode,
        "title": args.title,
        "angle": args.angle,
        "word_count": wc,
        "caption_path": str(txt_path),
        "meta_path": str(meta_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "text": text,
    }

    meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
