---
name: tao-creative-fb
description: >-
  Tạo full creative Facebook cho business page theo đúng brand voice Chăm Chăm, luôn bắt buộc ra CẢ ẢNH VÀ VĂN BẢN đi cùng nhau.
  What it does: (1) Content Free cho Page hằng ngày: sinh ý tưởng, sau đó tạo 1 ảnh + 1 caption hoàn chỉnh và có thể đăng lên Facebook Page; (2) Creative Ads: tạo 3 bộ ads, mỗi bộ là 1 ảnh ads + 1 ad copy ghép cặp để dùng trong Ads Manager.
  When to use: khi cần sản xuất bài organic hằng ngày hoặc cần bộ creative cho chiến dịch quảng cáo.
  Trigger phrases:
  - Mode Content Free: "tạo content cho ngày mai", "gen bài Page", "content free", "content organic"
  - Mode Creative Ads: "tạo creative ads", "gen ads", "cần creative cho chiến dịch"
---

# Tao Creative FB (Cap 3)

## Mục tiêu cốt lõi
- Mỗi output luôn là 1 cặp hoàn chỉnh: `ẢNH + VĂN BẢN`.
- Bài đăng FB hoàn chỉnh = `ảnh + caption`.
- Creative ads hoàn chỉnh = `ảnh ads + ad copy`.
- Không bao giờ trả ra chỉ ảnh hoặc chỉ text.

## Brand voice bắt buộc
- Giọng ấm, gần gũi, đời thường, viết như nói.
- Câu ngắn, rõ ý, tránh vòng vo.
- Tránh hàn lâm, sáo rỗng, quá thương mại, phóng đại công dụng.
- Có CTA rõ ràng theo đúng mode.

## Inputs & môi trường
- Python 3.10+
- Packages: `openai`, `requests`, `python-dotenv`
- `.env` cần có:
  - `OPENAI_API_KEY`
  - `FB_PAGE_ID`
  - `FB_PAGE_TOKEN`
  - `DRY_RUN=true|false`

## MODE 1 — CONTENT FREE (auto-post Page hằng ngày)

### Trigger
- "tạo content cho ngày mai"
- "gen bài Page"
- "content free"
- "content organic"

### Luồng xử lý
1. Bước A: Tạo 3 ý tưởng ngắn (mỗi ý gồm `tiêu đề + angle`) và gửi user chọn.
2. Bước B: Khi user chọn 1 ý tưởng, tạo full content cho đúng ý đó:
- 1 ảnh `1024x1024` bằng `gpt-image-1` với `quality=low`.
- 1 caption `~80-150 từ` gồm: hook + body + soft CTA.
3. Bước C: Hiển thị preview đầy đủ: ảnh + caption.
4. Bước D: Chỉ khi user xác nhận OK mới đăng Facebook:
- Endpoint: `/{page-id}/photos`
- Params: `url=image_url`, `caption=caption_text`

### Script mapping
- Gen ảnh: `python scripts/gen_image.py --mode organic --title "..." --angle "..." --size 1024x1024 --quality low`
- Gen caption: `python scripts/gen_caption.py --mode organic --title "..." --angle "..."`
- Post Facebook: `python scripts/post_facebook.py --image-url "..." --caption-file "..."`

## MODE 2 — CREATIVE ADS (gen thủ công, không auto đăng)

### Trigger
- "tạo creative ads"
- "gen ads"
- "cần creative cho chiến dịch"

### Luồng xử lý
1. Tạo đúng 3 bộ creative, mỗi bộ luôn gồm:
- 1 ảnh ads (`gpt-image-1`, `quality=medium`, có khoảng trống overlay text nếu cần)
- 1 ad copy hoàn chỉnh `~80-150 từ` (hook mạnh + USP + CTA rõ)
2. Ba bộ phải khác angle:
- `pain point`
- `solution`
- `social proof`
3. Không tự đăng Facebook. Chỉ trả bộ nội dung để user paste vào Ads Manager.

### Script mapping
- Gen 3 ảnh ads: gọi `scripts/gen_image.py` theo từng angle bắt buộc.
- Gen 3 ad copy: gọi `scripts/gen_caption.py` theo từng angle bắt buộc.

## Chế độ test an toàn
- Nếu `DRY_RUN=true`:
- Không post Facebook thật.
- Chỉ in preview ra console.
- Lưu ảnh + caption/copy vào thư mục `outputs/`.

## Error handling
- Lỗi OpenAI: log lỗi rõ + retry 1 lần.
- Lỗi Facebook API: trả lỗi rõ ràng (HTTP status + response body).

## Guardrails chất lượng
- Kiểm tra đủ cặp `image + text` trước khi trả kết quả.
- Kiểm tra độ dài copy/caption nằm trong khoảng 80-150 từ.
- Với Mode 2, kiểm tra đủ 3 angle khác nhau trước khi hoàn tất.
- Với Mode 1, không gọi post endpoint nếu chưa có xác nhận từ user.
