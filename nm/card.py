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
    out_im = Image.alpha_composite(base.convert("RGBA"), ov); out_im.alpha_composite(logo(), (40, 36))
    out_im.convert("RGB").save(out_path, quality=92)


ORBIT = "ПОЛИТИКА • ЭКОНОМИКА • МИР • НАУКА • ОБЩЕСТВО • "


def logo(h=110):
    """Логотип: глобус с континентами, по орбите летят слова рубрик, справа «НОВОСТИМАНИЯ»."""
    import math
    S = 6; H = h * S; R = H * 0.30; cx = cy = H / 2
    f_word = ImageFont.truetype(FB, int(H * 0.29)); tw_ = f_word.getlength("НОВОСТИМАНИЯ") + 5 * S * 11
    im = Image.new("RGBA", (int(H + tw_ + H * 0.2), H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).ellipse([cx - R, cy - R + S * 3, cx + R, cy + R + S * 3], fill=(0, 0, 0, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(S * 4)))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=GLOBE)
    land = (47, 112, 220)
    d.chord([cx - R * 0.75, cy - R * 0.75, cx + R * 0.05, cy + R * 0.05], 160, 340, fill=land)
    d.chord([cx - R * 0.05, cy - R * 0.1, cx + R * 0.7, cy + R * 0.8], 300, 120, fill=land)
    w = max(1, int(S * 1.5))
    d.ellipse([cx - R, cy - R * 0.38, cx + R, cy + R * 0.38], outline=GRID, width=w)
    d.ellipse([cx - R * 0.42, cy - R, cx + R * 0.42, cy + R], outline=GRID, width=w)
    d.line([(cx, cy - R), (cx, cy + R)], fill=GRID, width=w)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=WHITE, width=int(S * 2.2))
    # слова на орбите: наклонённый эллипс, передняя половина поверх глобуса, задняя бледнее
    a, b, tilt = H * 0.47, H * 0.17, math.radians(-18); fo = ImageFont.truetype(FB, int(H * 0.095))
    pts, t, t0 = [], math.pi * 0.95, math.pi * 0.95
    for ch in ORBIT * 2:
        x, y = a * math.cos(t), b * math.sin(t)
        X = cx + x * math.cos(tilt) - y * math.sin(tilt); Y = cy + x * math.sin(tilt) + y * math.cos(tilt)
        dx, dy = a * math.sin(t), -b * math.cos(t); ang = math.degrees(math.atan2(dy * math.cos(tilt) + dx * math.sin(tilt), dx * math.cos(tilt) - dy * math.sin(tilt)))
        front = math.sin(t) > -0.15
        g = Image.new("RGBA", (int(H * 0.14),) * 2, (0, 0, 0, 0))
        ImageDraw.Draw(g).text((g.width / 2, g.height / 2), ch, font=fo, fill=(YEL if front else PALE) + (255 if front else 150,), anchor="mm")
        g = g.rotate(-ang, resample=Image.BICUBIC); pts.append((front, g, X, Y))
        t -= (fo.getlength(ch) + S * 1.2) / math.hypot(dx, dy)
        if t < t0 - 2 * math.pi + 0.05: break
    for front, g, X, Y in sorted(pts, key=lambda p: p[0]):
        im.alpha_composite(g, (int(X - g.width / 2), int(Y - g.height / 2)))
    x = H * 1.02; y = cy + H * 0.1
    for c in "НОВОСТИМАНИЯ":
        d.text((x + S * 2, y + S * 2), c, font=f_word, fill=(0, 0, 0, 120), anchor="ls")
        d.text((x, y), c, font=f_word, fill=WHITE, anchor="ls"); x += f_word.getlength(c) + 5 * S
    im = im.crop((0, 0, int(x + S * 4), H))
    return im.resize((im.width // S, h), Image.LANCZOS)


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
