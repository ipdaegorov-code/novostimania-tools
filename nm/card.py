"""Картинки поста 1080×1080: айдентика, квадрат без обрезки, бейджи, флаги, карточка.

python3 -m nm.card make   --photo P --out O --title T --subtitle S [--badge B] [--date D] [--credit C]
python3 -m nm.card make   --style big --photo P --out O --title T   # заголовок капсом внизу + логотип (основной стиль)
python3 -m nm.card square --src P --out O                   # квадрат расширением (размытый фон)
python3 -m nm.card crop   --src P --out O                   # квадрат обрезкой центра
python3 -m nm.card dim    --src P --out O [--k 0.8]         # затемнить верхние 2/3 (фон карточки)
python3 -m nm.card badge  --card P --portrait F --name N --out O [--slot 1 --of 2]
python3 -m nm.card flags  --src P --out O --countries Russia "United States"   # плашка в углу
python3 -m nm.card flagrow --src P --out O --countries Russia "United States" [--pos center|low]  # крупно в ряд
python3 -m nm.card navy   --out O                           # синий фон канала (крайний случай)
"""
import argparse, os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from nm.common import out, die, http, UA

NAVY = (15, 42, 92); GLOBE = (30, 79, 168); GRID = (61, 111, 196); RED = (229, 50, 45)
YEL = (255, 201, 60); WHITE = (255, 255, 255); PALE = (191, 211, 255)


def font_path():
    p = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    if os.path.exists(p):
        return p
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True)
        if r.stdout and os.path.exists(r.stdout):
            return r.stdout
    except Exception:
        pass
    die("не найден жирный шрифт (поставь fonts-liberation)")


FB = font_path()


def make(photo_path, out_path, title, subtitle, badge="ПОЛИТИКА", date="", size=1080, credit=""):
    S = 2; base = Image.open(photo_path).convert("RGB"); side = min(base.size)
    l, t = (base.width - side) // 2, (base.height - side) // 2
    base = base.crop((l, t, l + side, t + side)).resize((size, size), Image.LANCZOS); W = size * S; k = size / 1264
    ov = Image.new("RGBA", (W, W), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    P = lambda v: v * k * S; F = lambda sz: ImageFont.truetype(FB, int(round(sz * k * S)))

    def tw(x, f, sp): return sum(f.getlength(c) for c in x) + P(sp) * (len(x) - 1)

    def text(x, y, s, f, fill, sp=0, anchor='l'):
        w = tw(s, f, sp)
        if anchor == 'r': x -= w
        for c in s:
            d.text((x, y), c, font=f, fill=fill, anchor='ls'); x += f.getlength(c) + P(sp)
    top = P(760)
    for y in range(int(top), W):
        a = min(1, (y - top) / (W - top) * 1.35); d.line([(0, y), (W, y)], fill=NAVY + (int(238 * a),))
    fb = F(30); bw = tw(badge, fb, 3) + P(86); d.rounded_rectangle([P(48), P(48), P(48) + bw, P(104)], radius=P(6), fill=RED)
    d.ellipse([P(62), P(68), P(78), P(84)], fill=WHITE); text(P(90), P(87), badge, fb, WHITE, sp=3)
    mw = P(1264 - 120); sz = 76
    while tw(title, F(sz), 1) > mw and sz > 36: sz -= 2
    text(P(60), P(1010), title, F(sz), WHITE, sp=1); d.rectangle([P(60), P(1034), P(230), P(1044)], fill=RED)
    ss = 34
    while tw(subtitle, F(ss), 5) > mw and ss > 20: ss -= 1
    text(P(60), P(1100), subtitle, F(ss), YEL, sp=5)
    cx, cy, r = P(84), P(1206), P(24); d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GLOBE)
    d.ellipse([cx - r, cy - r * 0.38, cx + r, cy + r * 0.38], outline=GRID, width=int(P(2)))
    d.ellipse([cx - r * 0.38, cy - r, cx + r * 0.38, cy + r], outline=GRID, width=int(P(2)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=int(P(3))); text(P(124), P(1215), "НОВОСТИМАНИЯ", F(28), YEL, sp=6)
    text(W - P(60), P(1215), date, F(26), PALE, sp=3, anchor='r')
    if credit:
        fc = F(19); x = W - P(60)
        text(x + P(2), P(922), credit, fc, (0, 0, 0, 170), anchor='r'); text(x, P(920), credit, fc, (255, 255, 255, 200), anchor='r')
    ov = ov.resize((size, size), Image.LANCZOS)
    Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB").save(out_path, quality=92)


def wrap(words, f, width, gap):
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and sum(f.getlength(c) for c in t) + gap * (len(t) - 1) > width:
            lines.append(cur); cur = w
        else:
            cur = t
    return lines + [cur]


def make_big(photo_path, out_path, title, size=1080):
    """Стиль «заголовок»: фото на весь кадр, логотип в углу, крупный заголовок капсом внизу (2–3 строки)."""
    S = 2; base = Image.open(photo_path).convert("RGB"); side = min(base.size)
    l, t = (base.width - side) // 2, (base.height - side) // 2
    base = base.crop((l, t, l + side, t + side)).resize((size, size), Image.LANCZOS); W = size * S
    ov = Image.new("RGBA", (W, W), (0, 0, 0, 0)); d = ImageDraw.Draw(ov); F = lambda sz: ImageFont.truetype(FB, int(sz * S))
    top = W * 0.42
    for y in range(int(top), W):
        a = min(1, max(0, (y - top) / (W - top)) ** 0.8 * 1.15); d.line([(0, y), (W, y)], fill=NAVY + (int(235 * a),))
    words = title.upper().split(); mw = (size - 120) * S; sz = 92
    while True:
        f = F(sz); lines = wrap(words, f, mw, 0)
        if (len(lines) <= 3 and max(f.getlength(x) for x in lines) <= mw) or sz <= 48: break
        sz -= 2
    lh = sz * 1.08 * S; y0 = (size - 64) * S - lh * (len(lines) - 1)
    for i, s in enumerate(lines):
        d.text((60 * S, y0 + i * lh), s, font=f, fill=WHITE, anchor="ls")
    d.rectangle([60 * S, y0 - lh + 2 * S - 22 * S, 190 * S, y0 - lh - 12 * S], fill=RED)
    ov = ov.resize((size, size), Image.LANCZOS)
    out_im = Image.alpha_composite(base.convert("RGBA"), corner_glow(size, NAVY))
    out_im.alpha_composite(ov); out_im.alpha_composite(logo(), (20, 14))
    out_im.convert("RGB").save(out_path, quality=92)


def _pill(text, f, fill=None, fg=WHITE, outline=None, dot=None, pad=0.55):
    h = f.size * 1.9; w = f.getlength(text) + h * pad * 2 + (h * 0.55 if dot else 0)
    im = Image.new("RGBA", (int(w) + 4, int(h) + 4), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([2, 2, w, h], radius=h / 2, fill=fill, outline=outline, width=max(1, int(f.size * 0.08)))
    x = 2 + h * pad
    if dot:
        r = h * 0.16; d.ellipse([x, 2 + h / 2 - r, x + 2 * r, 2 + h / 2 + r], fill=dot); x += h * 0.55
    d.text((x, 2 + h / 2), text, font=f, fill=fg, anchor="lm")
    return im


def logo_icon(size=600, small=False):
    """Глобус из промо: сфера с сеткой и материками, три орбиты, плашки рубрик, LIVE и 24/7.
    small=True — для угла карточки: без плашек и 24/7, только крупная красная LIVE."""
    import math
    S = 2; W = size * S; c = W / 2; R = W * 0.27
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ORB = (150, 190, 255, 255); lw = max(3, int(W * 0.013))

    def orbit(rx, ry, ang, side, front):
        """Половина орбиты: side — какая сторона ближе к зрителю (down/right/left); задняя прячется за шар."""
        o = Image.new("RGBA", (W, W), (0, 0, 0, 0)); d = ImageDraw.Draw(o)
        d.ellipse([c - rx, c - ry, c + rx, c + ry], outline=ORB, width=lw)
        h = Image.new("L", (W, W), 0); hd = ImageDraw.Draw(h)
        box = {"down": [0, c, W, W], "right": [c, 0, W, W], "left": [0, 0, c, W]}[side]
        hd.rectangle(box, fill=255)
        if not front: h = Image.eval(h, lambda v: 255 - v)
        o.putalpha(Image.composite(o.getchannel("A"), Image.new("L", (W, W), 0), h))
        o = o.rotate(ang, resample=Image.BICUBIC, center=(c, c))
        if not front:
            m = Image.new("L", (W, W), 255); ImageDraw.Draw(m).ellipse([c - R, c - R, c + R, c + R], fill=0)
            o.putalpha(Image.composite(o.getchannel("A"), Image.new("L", (W, W), 0), m))
        return o
    orbits = [(W * 0.47, W * 0.13, 0, "down"), (W * 0.15, W * 0.47, 28, "right"), (W * 0.15, W * 0.47, -28, "left")]
    for o in orbits:
        im.alpha_composite(orbit(*o, front=False))
    # сфера
    g = Image.new("RGBA", (W, W), (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
    for i in range(int(R), 0, -2):
        t = i / R; col = tuple(int(a + (b - a) * (1 - t)) for a, b in zip((22, 70, 170), (70, 140, 240)))
        ox, oy = (1 - t) * R * 0.25, (1 - t) * R * 0.3
        gd.ellipse([c - i - ox, c - i - oy, c + i - ox, c + i - oy], fill=col + (255,))
    mask = Image.new("L", (W, W), 0); ImageDraw.Draw(mask).ellipse([c - R, c - R, c + R, c + R], fill=255)
    land = Image.new("RGBA", (W, W), (0, 0, 0, 0)); ld = ImageDraw.Draw(land); LC = (90, 150, 245, 200)
    P = lambda pts: [(c + x * R, c + y * R) for x, y in pts]
    ld.polygon(P([(-0.75, -0.55), (-0.35, -0.7), (-0.1, -0.45), (-0.3, -0.2), (-0.45, 0.05), (-0.6, -0.05), (-0.85, -0.25)]), fill=LC)
    ld.polygon(P([(-0.4, 0.1), (-0.15, 0.15), (-0.05, 0.4), (-0.2, 0.75), (-0.35, 0.6), (-0.45, 0.3)]), fill=LC)
    ld.polygon(P([(0.15, -0.45), (0.5, -0.5), (0.7, -0.25), (0.55, 0.0), (0.6, 0.35), (0.4, 0.6), (0.25, 0.3), (0.2, 0.0), (0.1, -0.2)]), fill=LC)
    gd = ImageDraw.Draw(land); GL = (150, 190, 255, 140); gw = max(1, int(W * 0.003))
    for k in (-0.6, -0.3, 0, 0.3, 0.6):
        yy = c + k * R; hw = R * math.sqrt(1 - k * k); gd.ellipse([c - hw, yy - hw * 0.12, c + hw, yy + hw * 0.12], outline=GL, width=gw)
    for k in (0.25, 0.6, 0.9):
        gd.ellipse([c - R * k, c - R, c + R * k, c + R], outline=GL, width=gw)
    gd.line([(c, c - R), (c, c + R)], fill=GL, width=gw)
    g.alpha_composite(land); g.putalpha(Image.composite(g.getchannel("A"), Image.new("L", (W, W), 0), mask))
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0)); ImageDraw.Draw(glow).ellipse([c - R * 1.08, c - R * 1.08, c + R * 1.08, c + R * 1.08], fill=(80, 140, 255, 90))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(W * 0.02))); im.alpha_composite(g)
    for o in orbits:
        im.alpha_composite(orbit(*o, front=True))
    d = ImageDraw.Draw(im)
    for x, y in ((0.15, -0.55), (-0.55, -0.35), (-0.25, 0.4)):
        X, Y = c + x * R, c + y * R; r = R * 0.035
        d.ellipse([X - r, Y - r, X + r, Y + r], fill=YEL); d.ellipse([X - r * 2.3, Y - r * 2.3, X + r * 2.3, Y + r * 2.3], outline=YEL + (200,), width=gw)
    LIVE = dict(fill=RED + (255,), fg=WHITE, outline=RED + (255,), dot=(230, 230, 240))
    if small:
        pl = _pill("LIVE", ImageFont.truetype(FB, int(W * 0.1)), **LIVE)
        im.alpha_composite(pl, (int(W * 0.99 - pl.width), int(W * 0.04)))
        return im.resize((size, size), Image.LANCZOS)
    fp = ImageFont.truetype(FB, int(W * 0.05)); PILL = (18, 45, 105, 235); PO = (110, 150, 230, 255); TX = (215, 228, 255)
    for txt, x, y, kw in (("ЭКОНОМИКА", 0.27, 0.06, {}), ("ПОЛИТИКА", 0.47, 0.86, {}),
                          ("ТЕХНОЛОГИИ", 0.52, 0.5, dict(fg=WHITE)), ("LIVE", 0.86, 0.43, LIVE)):
        pl = _pill(txt, fp, kw.get("fill", PILL), kw.get("fg", TX), kw.get("outline", PO), kw.get("dot"))
        im.alpha_composite(pl, (int(W * x - pl.width / 2), int(W * y - pl.height / 2)))
    r = W * 0.065; X, Y = W * 0.08, W * 0.6
    d.ellipse([X - r, Y - r, X + r, Y + r], fill=YEL); d.text((X, Y), "24/7", font=ImageFont.truetype(FB, int(W * 0.042)), fill=NAVY, anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


def logo(h=180):
    """Логотип для угла карточки: глобус из промо с орбитами и LIVE."""
    return logo_icon(h * 2, small=True).resize((h, h), Image.LANCZOS)


def corner_glow(size, color, r=210, k=0.92):
    """Градиент в левом верхнем углу под логотип."""
    m = Image.new("L", (size, size), 0); d = ImageDraw.Draw(m)
    for i in range(r, 0, -4):
        d.ellipse([-i, -i, i, i], fill=int(255 * k * (1 - i / r) ** 0.7))
    g = Image.new("RGBA", (size, size), color + (255,)); g.putalpha(m); return g


def square_fit(src, dst, size=1080):
    im = Image.open(src).convert("RGB"); s = max(im.size) / size
    bg = im.resize((int(im.width * size / min(im.size)) + 1, int(im.height * size / min(im.size)) + 1), Image.LANCZOS)
    l, t = (bg.width - size) // 2, (bg.height - size) // 2
    bg = bg.crop((l, t, l + size, t + size)).filter(ImageFilter.GaussianBlur(40)); bg = ImageEnhance.Brightness(bg).enhance(0.55)
    fg = im.resize((int(im.width / s), int(im.height / s)), Image.LANCZOS); bg.paste(fg, ((size - fg.width) // 2, (size - fg.height) // 2)); bg.save(dst, quality=92)


def crop_square(src, dst, size=1080):
    im = Image.open(src).convert("RGB"); s = min(im.size); l, t = (im.width - s) // 2, (im.height - s) // 2
    im.crop((l, t, l + s, t + s)).resize((size, size), Image.LANCZOS).save(dst, quality=92)


def dim_top(src, dst, k=0.8, size=1080):
    crop_square(src, dst, size)
    im = Image.open(dst).convert("RGB"); h = size * 2 // 3; fade = 140
    dark = ImageEnhance.Brightness(im).enhance(k)
    mask = Image.new("L", (size, size), 0); md = ImageDraw.Draw(mask)
    md.rectangle([0, 0, size, h - fade], fill=255)
    for i in range(fade):
        md.line([(0, h - fade + i), (size, h - fade + i)], fill=int(255 * (1 - i / fade)))
    Image.composite(dark, im, mask).save(dst, quality=92)


def dim_all(src, dst, k=0.7, size=1080):
    crop_square(src, dst, size)
    ImageEnhance.Brightness(Image.open(dst).convert("RGB")).enhance(k).save(dst, quality=92)


def badge(card_path, portrait_path, name, out_path, x=None, y=70, D=360):
    base = Image.open(card_path).convert("RGBA"); S = 3
    p = Image.open(portrait_path).convert("RGB"); s = min(p.size)
    p = p.crop(((p.width - s) // 2, 0, (p.width - s) // 2 + s, s)).resize((D * S, D * S), Image.LANCZOS)
    m = Image.new("L", (D * S, D * S), 0); ImageDraw.Draw(m).ellipse([0, 0, D * S - 1, D * S - 1], fill=255)
    R = (D + 28) * S; ring = Image.new("RGBA", (R, R), (0, 0, 0, 0)); dr = ImageDraw.Draw(ring)
    dr.ellipse([0, 0, R - 1, R - 1], fill=RED + (255,)); dr.ellipse([6 * S, 6 * S, R - 6 * S - 1, R - 6 * S - 1], fill=WHITE + (255,)); ring.paste(p, (14 * S, 14 * S), m)
    ring = ring.resize((D + 28, D + 28), Image.LANCZOS)
    if x is None: x = 1080 - 60 - (D + 28)
    base.alpha_composite(ring, (x, y)); d = ImageDraw.Draw(base); f = ImageFont.truetype(FB, 30); t = name.upper(); w = d.textlength(t, font=f); cx = x + (D + 28) // 2
    d.rounded_rectangle([cx - w / 2 - 22, y + D + 4, cx + w / 2 + 22, y + D + 56], radius=8, fill=NAVY + (255,), outline=WHITE + (255,), width=2)
    d.text((cx, y + D + 30), t, font=f, fill=WHITE, anchor="mm"); base.convert("RGB").save(out_path, quality=92)


def badge_pos(slot, of):
    """Раскладка бейджей: 1 — справа D=360; 2 — D=300 справа и левее; 3 — D=240 в ряд."""
    if of <= 1: return dict(x=None, y=70, D=360)
    if of == 2: return dict(x=1080 - 60 - 328 * slot - 30 * (slot - 1), y=70, D=300)
    return dict(x=60 + (slot - 1) * (268 + 40), y=150, D=240)


_flag_cache = {}


def flag_png(country):
    """PNG флага с Wikimedia Commons (общественное достояние)."""
    if country in _flag_cache: return _flag_cache[country]
    cache = os.path.expanduser("~/.nm_flags"); os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, country.replace(" ", "_") + ".png")
    if os.path.exists(path) and os.path.getsize(path) > 500:
        _flag_cache[country] = path; return path
    from nm.photos import _wiki
    r = _wiki({"action": "query", "titles": f"File:Flag of {country}.svg", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 640})
    pages = r.get("query", {}).get("pages", {})
    info = next(iter(pages.values()), {}).get("imageinfo")
    if not info: die(f"флаг не найден: {country} (пиши как на Commons: Russia, the United States, Ukraine, China)")
    url = info[0].get("thumburl") or info[0]["url"]
    url = url.replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/").split("?")[0]
    import time
    for _ in range(4):
        data = http(url, raw=True)
        if data[:8] == b"\x89PNG\r\n\x1a\n": break
        time.sleep(45)
    else:
        die(f"не скачался флаг {country}")
    with open(path, "wb") as f: f.write(data)
    _flag_cache[country] = path
    return path


def _framed_flag(country, h):
    fl = Image.open(flag_png(country)).convert("RGBA"); w = int(fl.width * h / fl.height)
    fl = fl.resize((w, h), Image.LANCZOS); b = max(4, h // 22)
    fr = Image.new("RGBA", (w + 2 * b, h + 2 * b), WHITE + (255,)); fr.paste(fl, (b, b), fl)
    sh = Image.new("RGBA", (fr.width + 24, fr.height + 24), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([12, 16, fr.width + 12, fr.height + 16], fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(8)); sh.alpha_composite(fr, (12, 12))
    return sh


def flags_corner(src, dst, countries, h=90):
    base = Image.open(src).convert("RGBA"); x = base.width - 40
    for c in reversed(countries):
        f = _framed_flag(c, h); x -= f.width; base.alpha_composite(f, (x, 40)); x += 8
    base.convert("RGB").save(dst, quality=92)


def flags_row(src, dst, countries, pos="center"):
    base = Image.open(src).convert("RGBA"); n = len(countries); h = {1: 300, 2: 230, 3: 170}.get(n, 130)
    fs = [_framed_flag(c, h) for c in countries]; gap = 30; total = sum(f.width for f in fs) + gap * (n - 1)
    while total > base.width - 80:
        h = int(h * 0.9); fs = [_framed_flag(c, h) for c in countries]; total = sum(f.width for f in fs) + gap * (n - 1)
    x = (base.width - total) // 2; y = (base.height * 2 // 3 - fs[0].height) // 2 if pos == "center" else base.height * 2 // 3 - fs[0].height - 40
    for f in fs:
        base.alpha_composite(f, (x, y)); x += f.width + gap
    base.convert("RGB").save(dst, quality=92)


def navy(dst, size=1080):
    im = Image.new("RGB", (size, size), NAVY); d = ImageDraw.Draw(im)
    for i, r in enumerate(range(620, 120, -100)):
        c = GLOBE if i % 2 == 0 else GRID
        d.ellipse([size // 2 - r, size // 3 - r, size // 2 + r, size // 3 + r], outline=c, width=6)
    im.save(dst, quality=92)


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("make"); a.add_argument("--photo", required=True); a.add_argument("--out", required=True)
    a.add_argument("--title", required=True); a.add_argument("--subtitle", default=""); a.add_argument("--badge", default="ПОЛИТИКА")
    a.add_argument("--date", default=""); a.add_argument("--credit", default=""); a.add_argument("--style", default="classic", choices=["classic", "big"])
    for n in ("square", "crop"):
        a = sp.add_parser(n); a.add_argument("--src", required=True); a.add_argument("--out", required=True)
    a = sp.add_parser("dim"); a.add_argument("--src", required=True); a.add_argument("--out", required=True)
    a.add_argument("--k", type=float, default=0.8); a.add_argument("--all", action="store_true")
    a = sp.add_parser("badge"); a.add_argument("--card", required=True); a.add_argument("--portrait", required=True)
    a.add_argument("--name", required=True); a.add_argument("--out", required=True)
    a.add_argument("--slot", type=int, default=1); a.add_argument("--of", type=int, default=1)
    for n in ("flags", "flagrow"):
        a = sp.add_parser(n); a.add_argument("--src", required=True); a.add_argument("--out", required=True)
        a.add_argument("--countries", nargs="+", required=True); a.add_argument("--pos", default="center")
    a = sp.add_parser("navy"); a.add_argument("--out", required=True)
    g = ap.parse_args()
    if g.cmd == "make" and g.style == "big":
        make_big(g.photo, g.out, g.title)
    elif g.cmd == "make":
        if not g.date:
            from nm.common import now; g.date = now().strftime("%d.%m.%Y")
        make(g.photo, g.out, g.title, g.subtitle, g.badge, g.date, credit=g.credit)
    elif g.cmd == "square": square_fit(g.src, g.out)
    elif g.cmd == "crop": crop_square(g.src, g.out)
    elif g.cmd == "dim": (dim_all if g.all else dim_top)(g.src, g.out, g.k)
    elif g.cmd == "badge": badge(g.card, g.portrait, g.name, g.out, **badge_pos(g.slot, g.of))
    elif g.cmd == "flags": flags_corner(g.src, g.out, g.countries)
    elif g.cmd == "flagrow": flags_row(g.src, g.out, g.countries, g.pos)
    elif g.cmd == "navy": navy(g.out)
    out({"ok": True, "file": g.out})


if __name__ == "__main__":
    main()
