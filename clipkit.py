"""clipkit — вертикальное видео «Новостимания» по сценарию: озвучка, моушн-графика, субтитры, музыка.
Запуск: python3 clipkit.py scenario.json out.mp4 [models_dir] [preview]
"""
import json, math, random, re, subprocess, sys, wave, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

W, H, FPS, SR = 1080, 1920, 30, 48000
MD = sys.argv[3] if len(sys.argv) > 3 else "models"
FBLACK, FXB, FBOLD = f"{MD}/Montserrat-Black.ttf", f"{MD}/Montserrat-ExtraBold.ttf", f"{MD}/Montserrat-Bold.ttf"
GLOBE = (30, 79, 168); GRID = (61, 111, 196); RED = (229, 50, 45); YEL = (255, 201, 60)
WHITE = (255, 255, 255); PALE = (191, 211, 255); STEEL = (150, 160, 180)
OUTRO_SAY = "Подписывайся на Новостим+анию — завтра будет новое видео."
_fc = {}
def F(p, s):
    k = (p, int(s))
    if k not in _fc: _fc[k] = ImageFont.truetype(p, max(4, int(s)))
    return _fc[k]
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_io(t): t = clamp(t); return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2
def back(t, s=1.9): t = clamp(t) - 1; return t * t * ((s + 1) * t + s) + 1
def prog(t, a, d): return clamp((t - a) / d)
def fmt(v, dec): return (f"{v:,.{dec}f}").replace(",", " ").replace(".", ",")

# ======================= ОЗВУЧКА =======================
TOK = re.compile(r"\{([^|}]+)\|([^}]+)\}|(\S+)")
def parse(s):
    spoken, disp = [], []
    for m in TOK.finditer(s):
        if m.group(1):
            ws = m.group(2).split(); spoken += ws; disp.append((m.group(1), len(ws)))
        else:
            w = m.group(3)
            if re.search(r"\w", w): spoken.append(w); disp.append((w.replace("+", ""), 1))
            elif disp:
                spoken.append(w)
                sep = "" if re.fullmatch(r"[.,!?:;…»)]+", w) else " "
                disp[-1] = (disp[-1][0] + sep + w, disp[-1][1])
    return " ".join(spoken), disp
def letters(w): return re.sub(r"[^\wё]", "", w.lower().replace("+", ""))

def voice(scenes, work):
    import torch
    from faster_whisper import WhisperModel
    tts = torch.package.PackageImporter(f"{MD}/v4_ru.pt").load_pickle("tts_models", "model")
    asr = WhisperModel("base", device="cpu", compute_type="int8", download_root=MD)
    out = []
    for i, sc in enumerate(scenes):
        spoken, disp = parse(sc["say"])
        a = tts.apply_tts(text=spoken, speaker=sc.get("voice", "eugene"), sample_rate=SR, put_accent=True, put_yo=True).numpy()
        a = np.concatenate([np.zeros(int(.05 * SR)), a, np.zeros(int(.15 * SR))])
        x = (np.clip(a, -1, 1) * 32767).astype(np.int16)
        p = f"{work}/s{i}.wav"
        with wave.open(p, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(x.tobytes())
        a16 = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", p, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
        segs, _ = asr.transcribe(np.frombuffer(a16, np.float32), language="ru", word_timestamps=True)
        ww = [w for sg in segs for w in sg.words]
        dur = len(x) / SR
        xs, ys, pos = [0.0], [ww[0].start if ww else 0.05], 0
        for w in ww:
            n = len(letters(w.word))
            if n: xs += [pos + .01, pos + n]; ys += [w.start, w.end]; pos += n
        if pos == 0: xs, ys, pos = [0, 1], [0.05, dur - 0.15], 1
        sw = [w for w in spoken.split() if letters(w)]; tk = sum(len(letters(w)) for w in sw) or 1
        times, q = [], 0
        for w in sw:
            n = len(letters(w))
            times.append((float(np.interp(q / tk * pos, xs, ys)), float(np.interp((q + n) / tk * pos, xs, ys)))); q += n
        toks, k = [], 0
        for d, n in disp:
            seg = times[k:k + n] or [times[-1]]; k += n
            toks.append({"w": d, "s": seg[0][0], "e": seg[-1][1]})
        out.append({"dur": dur, "words": toks, "wav": p})
    return out

# ======================= КАРТИНКИ =======================
def load(path, side=2600):
    im = Image.open(path).convert("RGB")
    s = side / min(im.size)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    return ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(1.1)).enhance(1.1)
def kb(img, t, a, b, z0, z1, c0=(.5, .5), c1=(.5, .5)):
    p = ease_io(prog(t, a, max(.01, b - a))); z = z0 + (z1 - z0) * p
    cx = c0[0] + (c1[0] - c0[0]) * p; cy = c0[1] + (c1[1] - c0[1]) * p
    ch = img.height / z; cw = ch * W / H
    if cw > img.width: cw = img.width / z; ch = cw * H / W
    x = clamp(cx * img.width - cw / 2, 0, img.width - cw); y = clamp(cy * img.height - ch / 2, 0, img.height - ch)
    return img.resize((W, H), Image.BILINEAR, box=(x, y, x + cw, y + ch))

_cache = {}
def once(key, fn):
    if key not in _cache: _cache[key] = fn()
    return _cache[key]
def vignette():
    def mk():
        v = Image.new("L", (W // 4, H // 4), 0); ImageDraw.Draw(v).ellipse([-W // 8, -H // 10, W // 4 + W // 8, H // 4 + H // 10], fill=255)
        v = v.filter(ImageFilter.GaussianBlur(60)).resize((W, H), Image.BICUBIC)
        return Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [Image.eval(v, lambda x: int((255 - x) * .75))])
    return once("vig", mk)
def grad():
    def mk():
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
        for y in range(H):
            a = int(210 * ((y - H * .5) / (H * .5)) ** 1.3) if y > H * .5 else 0
            if y < 330: a = max(a, int(150 * (1 - y / 330)))
            d.line([(0, y), (W, y)], fill=(5, 8, 20, a))
        return g
    return once("grad", mk)

def logo(d, cx, cy, r, al=255):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GLOBE + (al,)); w = max(2, int(r * .09))
    d.ellipse([cx - r, cy - r * .38, cx + r, cy + r * .38], outline=GRID + (al,), width=w)
    d.ellipse([cx - r * .38, cy - r, cx + r * .38, cy + r], outline=GRID + (al,), width=w)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE + (al,), width=max(2, int(r * .12)))
def stext(base, cx, cy, s, path, size, fill, scale=1.0, alpha=1.0, stroke=0, maxw=W - 100):
    if alpha <= .01 or scale <= .01: return
    sz = size
    while F(path, sz).getlength(s) > maxw and sz > 30: sz -= 4
    f = F(path, sz * scale); bb = f.getbbox(s, stroke_width=stroke)
    tw, th = bb[2] - bb[0] + 50, bb[3] - bb[1] + 50
    L = Image.new("RGBA", (int(tw), int(th)), (0, 0, 0, 0))
    S = Image.new("RGBA", L.size, (0, 0, 0, 0))
    ImageDraw.Draw(S).text((tw / 2 + 4, th / 2 + 6), s, font=f, fill=(0, 0, 0, 170), anchor="mm")
    L.alpha_composite(S.filter(ImageFilter.GaussianBlur(6)))
    ImageDraw.Draw(L).text((tw / 2, th / 2), s, font=f, fill=fill + (255,), anchor="mm", stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    if alpha < 1: L.putalpha(Image.eval(L.getchannel("A"), lambda v: int(v * alpha)))
    base.alpha_composite(L, (int(cx - L.width / 2), int(cy - L.height / 2)))
def chip(base, x, y, s, bg, fg, size=40, slide=0.0, dot=True, path=FXB, right=False):
    f = F(path, size); w = f.getlength(s) + (86 if dot else 50); h = size * 1.75
    L = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * .22), fill=bg + (255,))
    if dot: d.ellipse([22, h / 2 - 8, 38, h / 2 + 8], fill=WHITE)
    d.text((60 if dot else 25, h / 2), s, font=f, fill=fg, anchor="lm")
    base.alpha_composite(L, (int((x - w if right else x) + slide), int(y)))
def wrap(text, f, mw):
    lines, cur = [], ""
    for w in text.split():
        s = (cur + " " + w).strip()
        if f.getlength(s) <= mw: cur = s
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# ======================= ТАЙМЛАЙН =======================
class Clip:
    def __init__(self, sc, vo, imgs):
        self.sc, self.vo, self.imgs = sc, vo, imgs
        self.starts, t = [], .45
        for v in vo: self.starts.append(t); t += v["dur"] + .25
        self.total = t + .9
        self.words = []
        for i, v in enumerate(vo):
            for w in v["words"]: self.words.append(dict(w, s=self.starts[i] + w["s"], e=self.starts[i] + w["e"], sc=i))
        self.chunks = self._chunks()
    def scene_at(self, t):
        k = 0
        for i, s in enumerate(self.starts):
            if t >= s - .15: k = i
        return k
    def bounds(self, i):
        a = 0 if i == 0 else self.starts[i] - .15
        b = self.total if i == len(self.starts) - 1 else self.starts[i + 1] - .15
        return a, b
    def wt(self, i, idx):
        ws = [w for w in self.words if w["sc"] == i]
        if not ws: return self.starts[i]
        if idx is None: idx = 0
        if idx < 0: idx = len(ws) + idx
        return ws[int(clamp(idx, 0, len(ws) - 1))]["s"]
    def _chunks(self):
        out, cur = [], []
        nosub = {i for i, s in enumerate(self.sc) if s["type"] in ("hook", "quote")}
        for w in self.words:
            if w["sc"] in nosub: continue
            txt = " ".join(x["w"] for x in cur + [w])
            if cur and (len(cur) >= 3 or len(txt) > 20 or cur[-1]["sc"] != w["sc"] or cur[-1]["w"].endswith((".", "!", "?", "—", ":", ","))):
                out.append(cur); cur = []
            cur.append(w)
        if cur: out.append(cur)
        for i, c in enumerate(out):
            nx = out[i + 1][0] if i + 1 < len(out) else None
            c[0]["cend"] = nx["s"] if nx and nx["sc"] == c[0]["sc"] else c[-1]["e"] + .35
        return out

    # ---------------- субтитры ----------------
    def subs(self, base, t):
        for c in self.chunks:
            a, b = c[0]["s"] - .04, c[0]["cend"]
            if not (a <= t < b): continue
            pop = back(prog(t, a, .16), 2.4); fade = 1 - prog(t, b - .08, .08)
            f = F(FBLACK, 78); sp = f.getlength(" ")
            lines, widths = [[]], [0]
            for src in c:
                w = src["w"].upper(); lw = f.getlength(w)
                if widths[-1] and widths[-1] + sp + lw > W - 140: lines.append([]); widths.append(0)
                lines[-1].append((w, src, lw)); widths[-1] += (sp if widths[-1] else 0) + lw
            L = Image.new("RGBA", (W, 360), (0, 0, 0, 0)); d = ImageDraw.Draw(L); y = 180 - (len(lines) - 1) * 50
            for ln, lw_ in zip(lines, widths):
                x = W / 2 - lw_ / 2
                for w, src, lw in ln:
                    act = src["s"] <= t < src["e"] + .05 or (t >= src["e"] and src is c[-1])
                    col = WHITE if t >= src["s"] else (210, 210, 220)
                    if act: d.rounded_rectangle([x - 14, y - 52, x + lw + 14, y + 52], radius=16, fill=RED + (235,))
                    d.text((x, y), w, font=f, fill=col, anchor="lm", stroke_width=7, stroke_fill=(0, 0, 0)); x += lw + sp
                y += 100
            s = .86 + .14 * pop
            L = L.resize((int(W * s), int(360 * s)), Image.BICUBIC)
            if fade < 1: L.putalpha(Image.eval(L.getchannel("A"), lambda v: int(v * fade)))
            ys = 1600 if self.sc[c[0]["sc"]]["type"] == "outro" else 1360
            base.alpha_composite(L, (int(W / 2 - L.width / 2), int(ys - L.height / 2)))

    # ---------------- сцены ----------------
    def bg(self, i, t, blur=0, dim=1.0, z=(1.0, 1.25)):
        a, b = self.bounds(i); s = self.sc[i]
        img = self.imgs.get(i)
        if img is None:
            fr = Image.new("RGB", (W, H), (8, 14, 34))
        else:
            fc = tuple(s.get("focus", (.5, .5)))
            zz = (z[1], z[0]) if s.get("zoom") == "out" else z
            fr = kb(img, t, a, b + .5, zz[0], zz[1], fc, fc)
        if blur: fr = fr.filter(ImageFilter.GaussianBlur(blur))
        if dim != 1: fr = ImageEnhance.Brightness(fr).enhance(dim)
        fr = fr.convert("RGBA"); fr.alpha_composite(grad()); return fr
    def label(self, fr, i, t, s):
        a, _ = self.bounds(i)
        if s.get("label"): chip(fr, 60, 250, s["label"].upper(), RED, WHITE, 42, slide=-500 * (1 - ease_out(prog(t, a, .35))))
        if s.get("sublabel"): chip(fr, 60, 345, s["sublabel"].upper(), (20, 30, 60), PALE, 28, slide=-500 * (1 - ease_out(prog(t, a + .15, .35))), dot=False, path=FBOLD)

    def hook(self, i, t, s):
        a, b = self.bounds(i)
        fr = self.bg(i, t, blur=0, dim=.55, z=(1.25, 1.0))
        lines = s.get("title", [])[:4]; acc = s.get("accent", len(lines) - 1)
        ws = [w for w in self.words if w["sc"] == i]; n = len(ws)
        span = max(1, int(n * .7))
        y = 520 - (len(lines) - 1) * 40
        for k, ln in enumerate(lines):
            st = ws[min(n - 1, int(k * span / max(1, len(lines))))]["s"] if n else a
            q = back(prog(t, st - .05, .22), 2.2)
            sz = 150 if len(ln) <= 9 else 118
            stext(fr, W / 2, y, ln.upper(), FBLACK, sz, YEL if k == acc else WHITE, scale=.5 + .5 * q, alpha=clamp(q * 1.5))
            y += sz * 1.05
        if s.get("subline"):
            st = ws[min(n - 1, int(n * .75))]["s"] if n else a + 1
            q = back(prog(t, st, .25), 2.0)
            if q > 0:
                f = F(FBLACK, 60); txt = s["subline"].upper(); tw = min(W - 120, f.getlength(txt) + 70)
                L = Image.new("RGBA", (int(tw), 110), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
                d.rounded_rectangle([0, 0, tw - 1, 109], radius=22, fill=RED + (255,))
                stext(L, tw / 2, 55, txt, FBLACK, 60, WHITE, maxw=tw - 50)
                s_ = .6 + .4 * q; L = L.resize((max(1, int(L.width * s_)), max(1, int(110 * s_))), Image.BICUBIC)
                fr.alpha_composite(L, (int(W / 2 - L.width / 2), int(y + 40)))
        return fr
    def photo(self, i, t, s):
        a, b = self.bounds(i)
        fr = self.bg(i, t, z=(1.0, 1.3)); d = ImageDraw.Draw(fr)
        if s.get("ring"):
            q = ease_out(prog(t, self.wt(i, 1), .7)); fc = s.get("focus", (.5, .5))
            if q > 0:
                r = 300 + 60 * prog(t, a, b - a); cx, cy = W / 2, H / 2 - 40
                d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * q, fill=YEL, width=9)
        self.label(fr, i, t, s); return fr
    def stat(self, i, t, s):
        a, b = self.bounds(i)
        fr = self.bg(i, t, blur=s.get("blur", 6), dim=.55, z=(1.1, 1.3))
        ta = self.wt(i, s.get("at_word", 0)); q = back(prog(t, ta - .1, .3), 2.2)
        if q > 0:
            v = float(s["value"]) * ease_out(prog(t, ta - .1, .9))
            txt = s.get("prefix", "") + fmt(v, int(s.get("decimals", 0))) + s.get("suffix", "")
            stext(fr, W / 2, 760, txt, FBLACK, 190, YEL, scale=.6 + .4 * q, alpha=clamp(q * 1.5))
            if s.get("caption"):
                k = ease_out(prog(t, ta + .25, .4)); f = F(FXB, 50)
                for j, ln in enumerate(wrap(s["caption"].upper(), f, W - 160)[:3]):
                    stext(fr, W / 2, 920 + j * 66 + 30 * (1 - k), ln, FXB, 50, WHITE, alpha=k)
        self.label(fr, i, t, s); return fr
    def compare(self, i, t, s):
        a, b = self.bounds(i)
        fr = self.bg(i, t, blur=14, dim=.35, z=(1.2, 1.35)); d = ImageDraw.Draw(fr)
        items = s["items"][:3]; vmax = max(float(x["value"]) for x in items) or 1
        base, top = 1160, 560; n = len(items); bw = 230 if n == 2 else 190
        gap = (W - 160 - n * bw) / (n + 1 if n > 1 else 2)
        ta = self.wt(i, s.get("at_word", 0)); dec = int(s.get("decimals", 0)); unit = s.get("unit", "")
        for k, it in enumerate(items):
            x0 = 80 + gap * (k + 1) + bw * k
            st = a + .15 if k < n - 1 else ta - .25
            q = ease_out(prog(t, st, 1.0 if k == n - 1 else .6))
            h = (base - top) * float(it["value"]) / vmax * q
            col = YEL if k == n - 1 else STEEL
            d.rounded_rectangle([x0, base - h, x0 + bw, base], radius=18, fill=col + (255,))
            stext(fr, x0 + bw / 2, base + 55, it["name"].upper(), FXB, 38, col, maxw=bw + 60)
            if q > 0:
                stext(fr, x0 + bw / 2, base - h - 55, fmt(float(it["value"]) * q, dec) + (" " + unit if unit else ""), FBLACK, 62, WHITE, maxw=bw + 120)
        d.line([(80, base), (W - 80, base)], fill=(255, 255, 255, 120), width=3)
        if s.get("badge"):
            tb = self.wt(i, s.get("badge_word", -1)); q = back(prog(t, tb, .3), 2.5)
            if q > 0:
                L = Image.new("RGBA", (300, 300), (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
                dl.ellipse([10, 10, 290, 290], fill=RED); dl.ellipse([24, 24, 276, 276], outline=WHITE, width=5)
                stext(L, 150, 150, s["badge"], FBLACK, 92, WHITE, maxw=230)
                sz = max(1, int(280 * q)); L = L.rotate(-12 * (1 - q), Image.BICUBIC).resize((sz, sz), Image.BICUBIC)
                fr.alpha_composite(L, (int(80 + gap + bw / 2 - sz / 2 + (40 if n == 2 else 0)), int(640 - sz / 2)))
        self.label(fr, i, t, s); return fr
    def quote(self, i, t, s):
        a, b = self.bounds(i)
        fr = self.bg(i, t, blur=3, dim=.4, z=(1.1, 1.25)); d = ImageDraw.Draw(fr)
        k = ease_out(prog(t, a + .1, .4))
        stext(fr, 140, 560 - 40 * (1 - k), "«", FBLACK, 260, RED, alpha=k)
        f = F(FXB, 62); lines = wrap(s.get("text", ""), f, W - 200)[:6]
        ws = [w for w in self.words if w["sc"] == i]
        for j, ln in enumerate(lines):
            st = a + .2 + j * .25; q = ease_out(prog(t, st, .35))
            L = Image.new("RGBA", (W, 100), (0, 0, 0, 0)); ImageDraw.Draw(L).text((100, 50), ln, font=f, fill=WHITE, anchor="lm", stroke_width=4, stroke_fill=(0, 0, 0))
            if q < 1: L.putalpha(Image.eval(L.getchannel("A"), lambda v: int(v * q)))
            fr.alpha_composite(L, (int(-40 * (1 - q)), 640 + j * 86))
        if s.get("author"):
            q = ease_out(prog(t, a + .6, .4)); y = 640 + len(lines) * 86 + 40
            d.rectangle([100, y, 100 + 140 * q, y + 8], fill=RED)
            stext(fr, W / 2, y + 70, "— " + s["author"].upper(), FXB, 40, YEL, alpha=q, maxw=W - 200)
        self.label(fr, i, t, s); return fr
    def outro(self, i, t, s):
        a, b = self.bounds(i)
        fr = self.bg(i, t, blur=18, dim=.35, z=(1.15, 1.3)); d = ImageDraw.Draw(fr)
        k = back(prog(t, a + .05, .4), 2.0)
        if k > 0:
            L = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); logo(ImageDraw.Draw(L), 200, 200, 150)
            sz = max(1, int(320 * k)); L = L.rotate(-90 * (1 - k)).resize((sz, sz), Image.BICUBIC)
            fr.alpha_composite(L, (int(W / 2 - sz / 2), int(560 - sz / 2)))
        k2 = ease_out(prog(t, a + .3, .4))
        stext(fr, W / 2, 820 + 40 * (1 - k2), "НОВОСТИМАНИЯ", FBLACK, 104, YEL, alpha=k2)
        stext(fr, W / 2, 920 + 40 * (1 - k2), "ВСЁ ГЛАВНОЕ ЗА МИНУТУ", FXB, 44, WHITE, alpha=k2)
        k3 = back(prog(t, a + .6, .35), 2.2)
        if k3 > 0:
            pulse = 1 + .05 * math.sin((t - a) * 9) * (1 if t > a + 1 else 0); clicked = t > a + 1.6
            L = Image.new("RGBA", (640, 170), (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
            dl.rounded_rectangle([5, 5, 635, 165], radius=40, fill=((120, 120, 130) if clicked else RED) + (255,))
            dl.text((320, 85), "ПОДПИСАН" if clicked else "ПОДПИСАТЬСЯ", font=F(FBLACK, 60), fill=WHITE, anchor="mm")
            sc_ = k3 * pulse; L = L.resize((max(1, int(640 * sc_)), max(1, int(170 * sc_))), Image.BICUBIC)
            fr.alpha_composite(L, (int(W / 2 - L.width / 2), int(1130 - L.height / 2)))
            tt = t - (a + 1.2)
            if tt > 0:
                mv = ease_out(clamp(tt / .4)); hx = W / 2 + 200 - 120 * mv; hy = 1330 - 150 * mv
                if tt > .4:
                    rr = 30 + 160 * clamp((tt - .4) / .5); al = int(200 * (1 - clamp((tt - .4) / .5)))
                    d.ellipse([hx - rr, hy - rr, hx + rr, hy + rr], outline=(255, 255, 255, al), width=6)
                d.ellipse([hx - 34, hy - 34, hx + 34, hy + 34], fill=(255, 255, 255, 230), outline=(0, 0, 0, 120), width=3)
        return fr

    def frame(self, t, badge):
        i = self.scene_at(t); s = self.sc[i]
        fr = getattr(self, s["type"])(i, t, s)
        for j in range(1, len(self.starts)):
            dt = t - (self.starts[j] - .15)
            if -.2 < dt < .2:
                e = 1 - abs(dt) / .2; z = 1 + .18 * e * e
                cw, ch = W / z, H / z
                fr = fr.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
                fr = fr.filter(ImageFilter.BoxBlur(int(10 * e)))
                fr.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(110 * e ** 3))))
        fr.alpha_composite(vignette()); d = ImageDraw.Draw(fr)
        if s["type"] != "outro":
            logo(d, 92, 120, 30); d.text((140, 120), "НОВОСТИМАНИЯ", font=F(FXB, 32), fill=YEL, anchor="lm")
            chip(fr, W - 60, 92, badge.upper(), RED, WHITE, 30, slide=300 * (1 - ease_out(prog(t, .1, .4))), right=True)
        self.subs(fr, t)
        fin = 1 - prog(t, self.total - .35, .35)
        if fin < 1: fr = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), fr, fin)
        return fr.convert("RGB")

    # ---------------- звук ----------------
    def audio(self, path):
        n = int(self.total * SR); tt = np.arange(n) / SR
        vo = np.zeros(n)
        for i, v in enumerate(self.vo):
            with wave.open(v["wav"]) as w: a = np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32767
            j = int(self.starts[i] * SR); vo[j:j + len(a)] += a[:n - j]
        mus = np.zeros(n); note = lambda m: 440 * 2 ** ((m - 69) / 12)
        rnd = random.Random(len(self.sc))
        prog_ = rnd.choice([[[45, 52, 57, 60, 64], [41, 48, 53, 57, 60], [43, 50, 55, 59, 62], [40, 47, 52, 56, 59]],
                            [[50, 57, 62, 65, 69], [46, 53, 58, 62, 65], [48, 55, 60, 64, 67], [45, 52, 57, 61, 64]],
                            [[43, 50, 55, 58, 62], [39, 46, 51, 55, 58], [41, 48, 53, 57, 60], [38, 45, 50, 54, 57]]])
        seg = 2.9
        for ci in range(int(self.total / seg) + 2):
            ch = prog_[ci % 4]; s0 = ci * seg; m = (tt >= s0 - .6) & (tt < s0 + seg + .6)
            if not m.any(): continue
            x = tt[m] - s0; env = np.clip((x + .6) / .8, 0, 1) * np.clip((seg + .6 - x) / .8, 0, 1)
            for k, nn in enumerate(ch):
                f = note(nn + (12 if k > 2 else 0))
                mus[m] += (np.sin(2 * np.pi * f * tt[m]) + .35 * np.sin(2 * np.pi * f * 1.003 * tt[m]) + .2 * np.sin(4 * np.pi * f * tt[m])) * env * (.05 if k else .09)
        beat = .6
        for k in range(int(self.total / beat) + 1):
            j = int((.45 + k * beat) * SR)
            if j >= n: break
            L = min(int(.35 * SR), n - j); x = np.arange(L) / SR; f = 55 * np.exp(-x * 9) + 42
            mus[j:j + L] += .35 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 7)
        env = np.convolve(np.abs(vo), np.ones(4800) / 4800, "same")
        duck = np.convolve(1 - .55 * np.clip(env * 18, 0, 1), np.ones(9600) / 9600, "same")
        sfx = np.zeros(n)
        L = int(.45 * SR); nz = np.random.RandomState(1).randn(L); wh = np.zeros(L); acc = acc2 = 0.0
        for q in range(L):
            acc += (.02 + .25 * q / L) * (nz[q] - acc); acc2 += .02 * (acc - acc2); wh[q] = acc - acc2
        wh = wh / (abs(wh).max() + 1e-9) * np.sin(np.pi * np.arange(L) / L) ** 2
        L2 = int(.8 * SR); x = np.arange(L2) / SR; im = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-x * 6) + 38) / SR) * np.exp(-x * 4.5)
        for j in range(1, len(self.starts)):
            p = int((self.starts[j] - .37) * SR); sfx[p:p + L] += .33 * wh[:n - p]
        hits = []
        for i, s in enumerate(self.sc):
            if s["type"] == "stat": hits.append(self.wt(i, s.get("at_word", 0)))
            if s["type"] == "compare":
                hits.append(self.wt(i, s.get("at_word", 0)))
                if s.get("badge"): hits.append(self.wt(i, s.get("badge_word", -1)))
            if s["type"] == "hook": hits.append(self.wt(i, int(len([w for w in self.words if w["sc"] == i]) * .45)))
        for h in hits:
            p = int(h * SR); sfx[p:p + L2] += .5 * im[:n - p]
        mix = vo + mus * .55 * duck + sfx
        mix *= np.clip((self.total - tt) / .6, 0, 1); mix = mix / (abs(mix).max() + 1e-9) * .89
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())

def build(scn_path, out, preview=None):
    S = json.load(open(scn_path)); base = os.path.dirname(os.path.abspath(scn_path))
    work = os.path.join(base, "work"); os.makedirs(work, exist_ok=True)
    scenes = [s for s in S["scenes"] if s.get("type") != "outro"]
    scenes.append({"type": "outro", "say": S.get("outro_say", OUTRO_SAY), "image": scenes[0].get("image")})
    imgs = {}
    for i, s in enumerate(scenes):
        if s.get("image"):
            p = s["image"] if os.path.isabs(s["image"]) else os.path.join(base, s["image"])
            imgs[i] = load(p)
    vo = voice(scenes, work)
    json.dump(vo, open(f"{work}/voice.json", "w"), ensure_ascii=False)
    c = Clip(scenes, vo, imgs); badge = S.get("badge", "ВИДЕО ДНЯ")
    if preview:
        res = []
        for i in range(len(scenes)):
            a, b = c.bounds(i); tp = a + (b - a) * .75
            c.frame(tp, badge).save(f"{work}/pv{i}.png"); res.append(f"{work}/pv{i}.png")
        return res
    c.audio(f"{work}/mix.wav")
    nf = int(c.total * FPS)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-i", f"{work}/mix.wav", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
                          "-af", "loudnorm=I=-14:TP=-1.5:LRA=9", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out],
                         stdin=subprocess.PIPE)
    for k in range(nf):
        p.stdin.write(c.frame(k / FPS, badge).tobytes())
    p.stdin.close(); p.wait()
    return out, round(c.total, 1)

if __name__ == "__main__":
    if len(sys.argv) > 4 and sys.argv[4] == "preview":
        print(build(sys.argv[1], sys.argv[2], preview=True))
    else:
        print(build(sys.argv[1], sys.argv[2]))
