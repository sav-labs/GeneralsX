"""Grade, scale and frame cameo renders like the retail USA command bar art.

GeneralsX @feature Claude 16/10/2026 Retail cameos are punchy (high contrast, saturated sky, warm sand),
slightly darkened toward the corners and sit in a dark navy bevel with a thin lighter inner edge.
"""

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

NAVY = (14, 22, 46)
EDGE = (64, 86, 128)


def grade(img):
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.15)
    w, h = img.size
    # Soft vignette: corners lose about a fifth of their light.
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((-w * 0.25, -h * 0.25, w * 1.25, h * 1.25), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))
    dark = ImageEnhance.Brightness(img).enhance(0.78)
    return Image.composite(img, dark, mask)


def bevel(img, scale=1):
    """Dark navy frame with a lighter inner line, `scale` pixels per game pixel."""
    w, h = img.size
    d = ImageDraw.Draw(img)
    outer = 2 * scale
    for i in range(outer):
        d.rectangle((i, i, w - 1 - i, h - 1 - i), outline=NAVY)
    d.rectangle((outer, outer, w - 1 - outer, h - 1 - outer), outline=EDGE, width=scale)
    return img


def finish(raw_path, out_stem, size):
    """Writes <out_stem>.png at game size and <out_stem>_4x.png for review."""
    img = grade(Image.open(raw_path).convert("RGB"))
    master = bevel(img.resize((size[0] * 4, size[1] * 4), Image.LANCZOS), 4)
    master.save(out_stem + "_4x.png")
    small = img.resize(size, Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1, percent=70, threshold=1))
    bevel(small).save(out_stem + ".png")
