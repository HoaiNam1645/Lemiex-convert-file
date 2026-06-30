"""
QR Code Generator Service - Simple Layout WITH SIZE + THEUNIV brand

Same as qr_generator_simple_size, but additionally renders a fixed brand line
"THEUNIV" centered BELOW the QR. This marks labels produced for the theuniff.com
system so they are never confused with the original peanut system's labels.

Cloned into its own module so the size endpoint (/qr/generate-simple-size) used
by the original system stays byte-for-byte unchanged.
"""

import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Dict, Any
import os

from services.b2_storage import upload_qr_to_b2

# Default brand text drawn under the QR. Overridable per-request via data['brand'].
BRAND_TEXT = "THEUNIV"


def generate_qr_image(data: Dict[str, Any]) -> bytes:
    order_id = data.get('order_id', '')
    order_item_id = data.get('order_item_id', '')
    pageqr = data.get('pageqr', '')
    size = str(data.get('size', '') or '').strip()
    brand_text = (str(data.get('brand', '') or '').strip() or BRAND_TEXT)

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(pageqr)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')
    qr_width, qr_height = qr_img.size

    # Layout constants
    side_padding = 40
    top_padding = 30
    gap_text_qr = 30
    gap_qr_brand = 22
    bottom_padding = 30
    title_font_size = 80

    # Resolve a bold font file once.
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    ]
    chosen_font_path = None
    for font_path in font_paths:
        if os.path.exists(font_path):
            chosen_font_path = font_path
            break

    # Build title: "{order_id} - {order_item_id}" + " - {size}" when size is present.
    if order_item_id != '':
        title_text = f"{order_id} - {order_item_id}"
    else:
        title_text = str(order_id)
    if size:
        title_text = f"{title_text} - {size}"

    tmp_img = Image.new('RGB', (10, 10))
    tmp_draw = ImageDraw.Draw(tmp_img)

    # Auto-shrink the title so it never grows wider than the QR.
    max_title_width = qr_width
    while True:
        font_title = (
            ImageFont.truetype(chosen_font_path, title_font_size)
            if chosen_font_path
            else ImageFont.load_default()
        )
        bbox = tmp_draw.textbbox((0, 0), title_text, font=font_title)
        title_w = bbox[2] - bbox[0]
        if title_w <= max_title_width or title_font_size <= 28 or not chosen_font_path:
            break
        title_font_size -= 4
    title_h = bbox[3] - bbox[1]

    # Brand line under the QR — auto-shrink to fit the QR width too.
    brand_font_size = 50
    while True:
        font_brand = (
            ImageFont.truetype(chosen_font_path, brand_font_size)
            if chosen_font_path
            else ImageFont.load_default()
        )
        bbrand = tmp_draw.textbbox((0, 0), brand_text, font=font_brand)
        brand_w = bbrand[2] - bbrand[0]
        if brand_w <= qr_width or brand_font_size <= 22 or not chosen_font_path:
            break
        brand_font_size -= 4
    brand_h = bbrand[3] - bbrand[1]

    # Canvas dimensions: width = widest of (title, qr, brand) + padding;
    # height = top + title + gap + qr + gap + brand + bottom
    content_width = max(title_w, qr_width, brand_w)
    canvas_width = content_width + side_padding * 2
    canvas_height = (
        top_padding + title_h + gap_text_qr + qr_height
        + gap_qr_brand + brand_h + bottom_padding
    )

    canvas = Image.new('RGB', (canvas_width, canvas_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Border
    draw.rectangle(
        [(0, 0), (canvas_width - 1, canvas_height - 1)],
        outline=(80, 80, 80),
        width=2,
    )

    # Title centered horizontally
    title_x = (canvas_width - title_w) // 2 - bbox[0]
    title_y = top_padding - bbox[1]
    draw.text((title_x, title_y), title_text, fill=(220, 0, 0), font=font_title)

    # QR centered horizontally, below title
    qr_x = (canvas_width - qr_width) // 2
    qr_y = top_padding + title_h + gap_text_qr
    canvas.paste(qr_img, (qr_x, qr_y))

    # Brand line ("THEUNIV") centered, below QR
    brand_x = (canvas_width - brand_w) // 2 - bbrand[0]
    brand_y = qr_y + qr_height + gap_qr_brand - bbrand[1]
    draw.text((brand_x, brand_y), brand_text, fill=(40, 40, 40), font=font_brand)

    output = BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    output.seek(0)
    return output.getvalue()


async def create_qr_and_upload(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate the size-labelled + THEUNIV-branded QR and upload to B2.

    Distinct '_szquniv.png' suffix so it can never collide with or overwrite the
    original size endpoint output ('_szqr.png') in the shared bucket.
    """
    image_bytes = generate_qr_image(data)

    order_id = data.get('order_id', 0)
    order_item_id = data.get('order_item_id', 0)
    import re

    def sanitize(s):
        return re.sub(r'[^a-zA-Z0-9]', '', str(s))

    stt = data.get('stt', 1)
    total = data.get('total', 1)

    parts = [
        str(order_id),
        str(order_item_id),
        sanitize(data.get('style', '')),
        sanitize(data.get('size', '')),
        sanitize(data.get('color', '')),
        str(stt),
        str(total),
    ]
    filename = "_".join(p for p in parts if p) + "_szquniv.png"

    url = upload_qr_to_b2(image_bytes, filename)
    return {"url": url}
