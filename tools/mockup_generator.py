"""Generate Etsy listing preview images from a spreadsheet design.

These are simple branded mockups — clean cover card with the title, niche,
and a few highlighted features. Etsy listings need 2000x2000 px images.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = (2000, 2000)
BG_COLOR = (245, 240, 232)        # warm cream
ACCENT = (47, 72, 88)              # deep slate
ACCENT_2 = (200, 100, 60)          # terracotta
TEXT_DARK = (40, 40, 40)
TEXT_LIGHT = (255, 255, 255)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try common system font paths; fall back to PIL default if none found."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def generate_cover(title: str, subtitle: str, features: list[str],
                   output_path: str | Path) -> Path:
    """Render a 2000x2000 listing cover image."""
    img = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([(0, 0), (CANVAS_SIZE[0], 60)], fill=ACCENT)
    # Bottom accent stripe
    draw.rectangle([(0, CANVAS_SIZE[1] - 30), CANVAS_SIZE], fill=ACCENT_2)

    # Subtitle (niche / category)
    sub_font = _load_font(54)
    draw.text((140, 220), subtitle.upper(), font=sub_font, fill=ACCENT_2)

    # Title — wrap if long
    title_font = _load_font(140, bold=True)
    lines = _wrap(draw, title, title_font, CANVAS_SIZE[0] - 280)
    y = 320
    for line in lines:
        draw.text((140, y), line, font=title_font, fill=ACCENT)
        y += 170

    # Divider
    y += 40
    draw.line([(140, y), (CANVAS_SIZE[0] - 140, y)], fill=ACCENT, width=4)

    # Feature bullets
    feat_font = _load_font(58)
    y += 80
    for feat in features[:5]:
        draw.ellipse([(140, y + 22), (172, y + 54)], fill=ACCENT_2)
        wrapped = _wrap(draw, feat, feat_font, CANVAS_SIZE[0] - 360)
        for ln in wrapped:
            draw.text((210, y), ln, font=feat_font, fill=TEXT_DARK)
            y += 76
        y += 30

    # Footer tag
    foot_font = _load_font(44)
    draw.text((140, CANVAS_SIZE[1] - 130),
              "INSTANT DOWNLOAD  •  EXCEL + GOOGLE SHEETS",
              font=foot_font, fill=ACCENT)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out


def generate_feature_image(title: str, callouts: list[tuple[str, str]],
                           output_path: str | Path) -> Path:
    """A second image showing 'what's inside' — header + numbered callouts."""
    img = Image.new("RGB", CANVAS_SIZE, "white")
    draw = ImageDraw.Draw(img)

    # Header band
    draw.rectangle([(0, 0), (CANVAS_SIZE[0], 280)], fill=ACCENT)
    h_font = _load_font(96, bold=True)
    draw.text((140, 90), title, font=h_font, fill=TEXT_LIGHT)
    sub_font = _load_font(48)
    draw.text((140, 200), "What's inside", font=sub_font, fill=(220, 220, 220))

    y = 380
    num_font = _load_font(80, bold=True)
    head_font = _load_font(60, bold=True)
    body_font = _load_font(44)
    for i, (heading, body) in enumerate(callouts[:5], start=1):
        # Number circle
        draw.ellipse([(140, y), (240, y + 100)], fill=ACCENT_2)
        bbox = draw.textbbox((0, 0), str(i), font=num_font)
        tw = bbox[2] - bbox[0]
        draw.text((190 - tw / 2, y + 5), str(i), font=num_font, fill=TEXT_LIGHT)

        # Heading + body
        draw.text((290, y - 5), heading, font=head_font, fill=ACCENT)
        wrapped = _wrap(draw, body, body_font, CANVAS_SIZE[0] - 440)
        ny = y + 70
        for ln in wrapped[:3]:
            draw.text((290, ny), ln, font=body_font, fill=TEXT_DARK)
            ny += 56
        y = max(ny, y + 160) + 30

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out
