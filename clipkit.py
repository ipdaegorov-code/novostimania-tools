"""clipkit — вертикальное видео «Новостимания» по сценарию: озвучка, моушн-графика, субтитры, музыка.
Запуск: python3 clipkit.py scenario.json out.mp4 [models_dir] [preview]
       python3 clipkit.py scenario.json cover.jpg models_dir cover   — обложка + cover_thumb.jpg
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

def voice_from_file(scenes, audio, work):
    """Готовая озвучка всего сценария одним файлом (например, ElevenLabs): режем по сценам по таймингам слов."""
    from faster_whisper import WhisperModel
    full = f"{work}/vo_full.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", audio, "-ac", "1", "-ar", str(SR), full], check=True)
    with wave.open(full) as w: A = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32767
    a16 = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", full, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    asr = WhisperModel("base", device="cpu", compute_type="int8", download_root=MD)
    segs, _ = asr.transcribe(np.frombuffer(a16, np.float32), language="ru", word_timestamps=True)
    ww = [w for sg in segs for w in sg.words]
    xs, ys, pos = [0.0], [ww[0].start if ww else 0.0], 0
    for w in ww:
        n = len(letters(w.word))
        if n: xs += [pos + .01, pos + n]; ys += [w.start, w.end]; pos += n
    parsed = [parse(sc["say"]) for sc in scenes]
    allw = [[w for w in sp.split() if letters(w)] for sp, _ in parsed]
    tk = sum(len(letters(w)) for ws in allw for w in ws) or 1
    times, q = [], 0
    for ws in allw:
        tt = []
        for w in ws:
            n = len(letters(w))
            tt.append((float(np.interp(q / tk * pos, xs, ys)), float(np.interp((q + n) / tk * pos, xs, ys)))); q += n
        times.append(tt)
    scn = []
    for i, (sp, disp) in enumerate(parsed):
        toks, k = [], 0
        for d, n in disp:
            s_ = times[i][k:k + n] or [times[i][-1]]; k += n
            toks.append({"w": d, "s": s_[0][0], "e": s_[-1][1]})
        scn.append({"words": toks})
    return {"continuous": True, "wav": full, "len": len(A) / SR, "scenes": scn}

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

class VideoSrc:
    """Кадры видеоролика для сцены: обрезка под 9:16, 30 fps, по кругу; читается последовательно."""
    def __init__(self, path, start=0.0, focus=(.5, .5)):
        self.path, self.start, self.focus = path, float(start), focus
        self.proc, self.idx = None, -1
    def _open(self, t0):
        if self.proc:
            self.proc.kill(); self.proc = None
        fx, fy = self.focus
        vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:(iw-{W})*{fx}:(ih-{H})*{fy},format=rgb24"
        self.proc = subprocess.Popen([ff_bin(), "-loglevel", "error", "-stream_loop", "-1", "-ss", f"{self.start + t0:.3f}", "-i", self.path,
                                      "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.idx = int(round(t0 * FPS)) - 1; self.last = None
    def frame(self, t):
        k = int(round(max(0.0, t) * FPS))
        if self.proc is None or k < self.idx or k > self.idx + 90: self._open(k / FPS)
        while self.idx < k:
            buf = self.proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3: break
            self.last = buf; self.idx += 1
        if self.last is None: return Image.new("RGB", (W, H), (8, 14, 34))
        return Image.frombytes("RGB", (W, H), self.last)
def ff_bin():
    import shutil
    return shutil.which("ffmpeg") or "ffmpeg"

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
        self.words = []
        if isinstance(vo, dict):  # одна непрерывная дорожка: сцены подстраиваются под голос
            off = .45; self.starts = []
            for i, v in enumerate(vo["scenes"]):
                t0 = off + (v["words"][0]["s"] if v["words"] else 0) - .12
                self.starts.append(max(off if i == 0 else 0, t0) if i else off)
                for w in v["words"]: self.words.append(dict(w, s=off + w["s"], e=off + w["e"], sc=i))
            self.total = off + vo["len"] + .9
        else:
            self.starts, t = [], .45
            for v in vo: self.starts.append(t); t += v["dur"] + .25
            self.total = t + .9
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
        img = self.imgs.get(i); vs = getattr(self, "vids", {}).get(i)
        zz = z if s.get("zoom") != "out" else (z[1], z[0]); p_ = ease_io(prog(t, a, max(.01, b + .5 - a)))
        self._zrel = (zz[0] + (zz[1] - zz[0]) * p_) / zz[0]
        if vs is not None:
            fr = vs.frame(t - a)
            zf = 1 + (zz[0] + (zz[1] - zz[0]) * p_ - 1) * .35  # лёгкий наезд и на видео
            z0f = 1 + (zz[0] - 1) * .35; self._zrel = zf / z0f
            if zf > 1.001:
                cw, ch = W / zf, H / zf; fr = fr.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
        elif img is None:
            fr = Image.new("RGB", (W, H), (8, 14, 34))
        else:
            fc = tuple(s.get("focus", (.5, .5)))
            zz = (z[1], z[0]) if s.get("zoom") == "out" else z
            fr = kb(img, t, a, b + .5, zz[0], zz[1], fc, fc)
        if blur: fr = fr.filter(ImageFilter.GaussianBlur(blur))
        if dim != 1: fr = ImageEnhance.Brightness(fr).enhance(dim)
        fr = fr.convert("RGBA"); fr.alpha_composite(grad()); return fr
    def callout(self, fr, i, t, s):
        co = s.get("callout")
        if not co: return
        zr = getattr(self, "_zrel", 1.0)
        px = W / 2 + (co.get("x", .5) * W - W / 2) * zr; py = H / 2 + (co.get("y", .5) * H - H / 2) * zr
        ta = self.wt(i, co.get("at_word", 1)); q = back(prog(t, ta - .1, .45), 2.0)
        if q <= 0: return
        d = ImageDraw.Draw(fr); R = co.get("r", 110) * q
        for k in range(2):  # пульс
            ph = ((t - ta) * 1.2 + k * .5) % 1.0 if t > ta + .4 else 0
            if ph > 0:
                rr = R + 90 * ph; al = int(200 * (1 - ph))
                d.ellipse([px - rr, py - rr, px + rr, py + rr], outline=YEL + (al,), width=4)
        d.ellipse([px - R, py - R, px + R, py + R], outline=YEL, width=9)
        txt = co.get("text", "").upper()
        if txt:
            k2 = ease_out(prog(t, ta + .15, .35)); up = co.get("pos", "up") == "up"
            lx = clamp(px, 260, W - 260); ly = py - R - 150 if up else py + R + 150
            d.line([(px, py - R if up else py + R), (px + (lx - px) * k2, py - (R + 95) * k2 if up else py + (R + 95) * k2)], fill=YEL, width=6)
            if k2 > .3:
                f = F(FBLACK, 50); tw = f.getlength(txt) + 60
                L = Image.new("RGBA", (int(tw), 90), (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
                dl.rounded_rectangle([0, 0, tw - 1, 89], radius=18, fill=RED + (255,)); dl.text((tw / 2, 45), txt, font=f, fill=WHITE, anchor="mm")
                sc = .7 + .3 * k2; L = L.resize((max(1, int(tw * sc)), max(1, int(90 * sc))), Image.BICUBIC)
                fr.alpha_composite(L, (int(lx - L.width / 2), int(ly - L.height / 2)))
    def label(self, fr, i, t, s):
        a, _ = self.bounds(i)
        self.callout(fr, i, t, s)
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
        fr = self.bg(i, t, blur=s.get("blur", 6), dim=s.get("dim", .55), z=(1.1, 1.3))
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
        fr = self.bg(i, t, blur=s.get("blur", 14), dim=s.get("dim", .35), z=(1.2, 1.35)); d = ImageDraw.Draw(fr)
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
        tracks = [(self.vo["wav"], .45)] if isinstance(self.vo, dict) else [(v["wav"], self.starts[i]) for i, v in enumerate(self.vo)]
        for path_, st in tracks:
            with wave.open(path_) as w: a = np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32767
            j = int(st * SR); vo[j:j + len(a)] += a[:n - j]
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

# ======================= ОБЛОЖКА =======================
def _cv_fit(text, path, size, maxw):
    while F(path, size).getlength(text) > maxw and size > 36: size -= 4
    return F(path, size)
def _cv_text(base, xy, s, font, fill, blur=10, off=(0, 8), alpha=190):
    L = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(L).text((xy[0] + off[0], xy[1] + off[1]), s, font=font, fill=(0, 0, 0, alpha), anchor="mm")
    base.alpha_composite(L.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(base).text(xy, s, font=font, fill=fill, anchor="mm")
def _cv_header(base, badge):
    d = ImageDraw.Draw(base)
    logo(d, 96, 150, 38); d.text((150, 150), "НОВОСТИМАНИЯ", font=F(FXB, 40), fill=YEL, anchor="lm")
    fb = F(FXB, 34); bw = fb.getlength(badge) + 86
    d.rounded_rectangle([W - 60 - bw, 118, W - 60, 182], radius=14, fill=RED)
    d.ellipse([W - 60 - bw + 22, 142, W - 60 - bw + 38, 158], fill=WHITE)
    d.text((W - 60 - bw + 60, 150), badge, font=fb, fill=WHITE, anchor="lm")
def _cv_cover_img(path, focus=(.5, .5), zoom=1.15):
    im = Image.open(path).convert("RGB")
    s = max(W / im.width, H / im.height) * zoom
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    x = int((im.width - W) * focus[0]); y = int((im.height - H) * focus[1])
    im = im.crop((x, y, x + W, y + H))
    return ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(1.15)).enhance(1.2)
def _cv_space(seed=3):
    rnd = random.Random(seed)
    im = Image.new("RGB", (W, H), (4, 6, 16))
    neb = Image.new("RGB", (W // 4, H // 4), (0, 0, 0)); dn = ImageDraw.Draw(neb)
    for cx, cy, r, c in [(50, 120, 150, (55, 30, 110)), (230, 260, 170, (120, 35, 45)), (140, 60, 110, (20, 55, 130))]:
        dn.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    im = Image.blend(im, neb.filter(ImageFilter.GaussianBlur(45)).resize((W, H), Image.BICUBIC), .45); d = ImageDraw.Draw(im)
    for _ in range(420):
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H * .8), rnd.uniform(.6, 2.8); v = rnd.randint(120, 255)
        d.ellipse([x - r / 2, y - r / 2, x + r / 2, y + r / 2], fill=(v, v, min(255, v + 25)))
    return im.convert("RGBA")
def _cv_planet(base, path, top_y, R=1500, rot=180):
    D = 2 * R; g = ImageEnhance.Contrast(Image.open(path).convert("RGB").rotate(rot).resize((D, D), Image.LANCZOS)).enhance(1.15)
    m = Image.new("L", (D, D), 0); ImageDraw.Draw(m).ellipse([0, 0, D - 1, D - 1], fill=255)
    cx, cy = W / 2, top_y + R
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - R - 40, cy - R - 40, cx + R + 40, cy + R + 40], fill=(255, 120, 60, 120))
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); layer.paste(g, (int(cx - R), int(cy - R)), m)
    base.alpha_composite(layer)
def _cv_bottom_shade(base, top_y):
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
    for y in range(int(top_y), H): ds.line([(0, y), (W, y)], fill=(5, 6, 14, int(min(235, 60 + (y - top_y) * .55))))
    base.alpha_composite(sh)
def _cv_shape(x0, x1, base_y, h, shape):
    w = x1 - x0
    if shape == "mountain_small":
        pts = [(0, 0), (.18, .35), (.3, .5), (.42, .82), (.5, 1), (.58, .86), (.66, .7), (.8, .42), (1, 0)]
    elif shape == "mountain":
        pts = [(0, 0), (.1, .22), (.22, .55), (.34, .84), (.42, .97), (.5, 1), (.58, .97), (.66, .84), (.78, .55), (.9, .22), (1, 0)]
    else:
        return None
    return [(x0 + px * w, base_y - py * h) for px, py in pts]
def _cv_fill(base, box_or_poly, tex_path, tint, snow=False, radius=26):
    poly = box_or_poly if isinstance(box_or_poly[0], tuple) else None
    if poly:
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]; ox, oy = min(xs), min(ys)
        bw, bh = int(max(xs) - ox) + 2, int(max(ys) - oy) + 2
    else:
        x0, y0, x1, y1 = box_or_poly; ox, oy, bw, bh = x0, y0, int(x1 - x0), int(y1 - y0)
    bw, bh = max(bw, 2), max(bh, 2)
    if tex_path:
        tex = Image.open(tex_path).convert("RGB"); s = max(bw / tex.width, bh / tex.height) * 1.2
        tex = tex.resize((max(bw, int(tex.width * s)), max(bh, int(tex.height * s))), Image.LANCZOS)
        tex = tex.crop(((tex.width - bw) // 2, (tex.height - bh) // 2, (tex.width - bw) // 2 + bw, (tex.height - bh) // 2 + bh))
        tex = Image.blend(tex, Image.new("RGB", tex.size, tint), .3)
    else:
        n = np.random.RandomState(5).rand(bh // 6 + 1, bw // 6 + 1)
        n = Image.fromarray((n * 255).astype("uint8")).resize((bw, bh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
        tex = Image.merge("RGB", [Image.eval(n, lambda v, c=c: int(c * (.75 + .5 * v / 255))) for c in tint])
    g = Image.new("L", (bw, bh)); gd = ImageDraw.Draw(g)
    for x in range(bw): gd.line([(x, 0), (x, bh)], fill=int(255 - 120 * x / bw))
    from PIL import ImageChops
    tex = ImageEnhance.Brightness(ImageChops.multiply(tex, Image.merge("RGB", [g] * 3))).enhance(1.35)
    m = Image.new("L", (bw, bh), 0); dm = ImageDraw.Draw(m)
    if poly: dm.polygon([(x - ox, y - oy) for x, y in poly], fill=255)
    else: dm.rounded_rectangle([0, 0, bw - 1, bh + radius], radius=radius, fill=255)
    L = Image.new("RGBA", (bw, bh), (0, 0, 0, 0)); L.paste(tex, (0, 0), m)
    if snow and poly:
        top = min(poly, key=lambda p: p[1]); tx, ty = top[0] - ox, top[1] - oy
        ImageDraw.Draw(L).polygon([(tx, ty), (tx - bw * .1, ty + bh * .2), (tx - bw * .03, ty + bh * .17), (tx + bw * .02, ty + bh * .22), (tx + bw * .1, ty + bh * .18)], fill=(240, 245, 255, 235))
    S = Image.new("RGBA", base.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(S)
    if poly: ds.polygon([(x + 14, y + 10) for x, y in poly], fill=(0, 0, 0, 150))
    else: ds.rounded_rectangle([ox + 14, oy + 10, ox + bw + 14, oy + bh + 10], radius=radius, fill=(0, 0, 0, 150))
    base.alpha_composite(S.filter(ImageFilter.GaussianBlur(14)))
    base.alpha_composite(L, (int(ox), int(oy)))
    d = ImageDraw.Draw(base)
    if poly: d.line(poly, fill=(255, 255, 255, 90), width=3)
    else: d.rounded_rectangle([ox, oy, ox + bw, oy + bh + radius], radius=radius, outline=(255, 255, 255, 90), width=3)
def _cv_badge(base, cx, cy, txt, D=250):
    L = Image.new("RGBA", (D, D), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    d.ellipse([6, 6, D - 7, D - 7], fill=RED); d.ellipse([20, 20, D - 21, D - 21], outline=WHITE, width=5)
    d.text((D / 2, D / 2), txt, font=_cv_fit(txt, FBLACK, 92, D - 60), fill=WHITE, anchor="mm")
    L = L.rotate(-10, Image.BICUBIC)
    S = Image.new("RGBA", base.size, (0, 0, 0, 0)); ImageDraw.Draw(S).ellipse([cx - D / 2 + 6, cy - D / 2 + 12, cx + D / 2 + 6, cy + D / 2 + 12], fill=(0, 0, 0, 140))
    base.alpha_composite(S.filter(ImageFilter.GaussianBlur(12))); base.alpha_composite(L, (int(cx - D / 2), int(cy - D / 2)))
def _cv_title(base, lines, accent, y0=330, sizes=(150, 170)):
    y = y0
    for k, ln in enumerate(lines[:3]):
        f = _cv_fit(ln, FBLACK, sizes[1] if k == accent else sizes[0], W - 110)
        _cv_text(base, (W / 2, y), ln, f, YEL if k == accent else WHITE); y += f.size * 1.0
    return y

def make_cover(S, base, out):
    """S — сценарий; S["cover"] — настройки обложки (см. README)."""
    cv = dict(S.get("cover") or {})
    P = lambda p: None if not p else (p if os.path.isabs(p) else os.path.join(base, p))
    scenes = S["scenes"]; hook = next((s for s in scenes if s["type"] == "hook"), scenes[0])
    cmp_ = next((s for s in scenes if s["type"] == "compare"), None)
    style = cv.get("style") or ("compare" if cmp_ else "title")
    badge = cv.get("badge", S.get("badge", "ВИДЕО ДНЯ")).upper()
    title = [t.upper() for t in cv.get("title", hook.get("title", []))]
    accent = cv.get("accent", hook.get("accent", len(title) - 1))
    img = P(cv.get("image") or hook.get("image") or scenes[0].get("image"))
    if style == "compare":
        items = cv.get("items") or (cmp_ or {}).get("items") or []
        unit = cv.get("unit", (cmp_ or {}).get("unit", "")); dec = int(cv.get("decimals", (cmp_ or {}).get("decimals", 0)))
        shape = cv.get("shape", "bar")
        im = _cv_space() if cv.get("space") else ImageEnhance.Brightness(_cv_cover_img(img).filter(ImageFilter.GaussianBlur(18))).enhance(.35).convert("RGBA")
        base_y = 1470
        if cv.get("ground_image"): _cv_planet(im, P(cv["ground_image"]), base_y - 20)
        _cv_bottom_shade(im, base_y - 20)
        n = len(items[:3]); vmax = max(float(i["value"]) for i in items[:3]) or 1; hmax = 640
        if n == 2: xs_ = [(70, 420), (360, 1050)] if shape == "mountain" else [(120, 420), (560, 960)]
        else: xs_ = [(80, 360), (400, 680), (720, 1000)]
        for k, it in enumerate(items[:3]):
            x0, x1 = xs_[k]; h = max(40, hmax * float(it["value"]) / vmax); main = k == n - 1
            tint = (230, 110, 55) if main else (110, 118, 135)
            tex = P(it.get("image")) if it.get("image") else (img if main else None)
            if shape == "mountain":
                poly = _cv_shape(x0, x1, base_y, h, "mountain" if main else "mountain_small")
                _cv_fill(im, poly, tex, tint, snow=not main and not it.get("image"))
            else:
                _cv_fill(im, (x0, base_y - h, x1, base_y), tex, tint)
            cx = (x0 + x1) / 2; lab = it.get("label") or (fmt(float(it["value"]), dec) + (" " + unit.upper() if unit else ""))
            big = main
            _cv_text(im, (cx, base_y - h - (150 if big else 120)), lab, _cv_fit(lab, FBLACK, 118 if big else 72, (x1 - x0) + 140), YEL if big else WHITE, blur=10, off=(0, 6))
            _cv_text(im, (cx, base_y - h - (70 if big else 55)), it["name"].upper(), _cv_fit(it["name"].upper(), FXB, 42 if big else 38, (x1 - x0) + 120), WHITE if big else (200, 210, 230), blur=6, off=(0, 3))
        if cv.get("badge_text") or (cmp_ or {}).get("badge"):
            x0, x1 = xs_[0]; h0 = hmax * float(items[0]["value"]) / vmax
            by = min(base_y - h0 - 330, 960); _cv_badge(im, (x0 + x1) / 2 + (0 if shape == "mountain" else 0), max(720, by), cv.get("badge_text") or cmp_["badge"])
        _cv_title(im, title, accent)
    else:
        im = _cv_cover_img(img, tuple(cv.get("focus", hook.get("focus", (.5, .45))))).convert("RGBA")
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
        for y in range(H):
            a = 70
            if y < 380: a = max(a, int(190 * (1 - y / 380)))
            if 520 < y < 1500: a = max(a, int(150 * (1 - abs(y - 1010) / 490)))
            if y > 1500: a = max(a, int(230 * (y - 1500) / 420))
            d.line([(0, y), (W, y)], fill=(5, 8, 20, a))
        im.alpha_composite(g); im.alpha_composite(vignette())
        y = _cv_title(im, title, accent, y0=560, sizes=(168, 168))
        sub = (cv.get("subline") or hook.get("subline") or "").upper()
        if sub:
            f = _cv_fit(sub, FBLACK, 72, W - 220); tw = f.getlength(sub) + 90
            L = Image.new("RGBA", (int(tw), 120), (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
            dl.rounded_rectangle([0, 0, tw - 1, 119], radius=24, fill=RED + (255,)); dl.text((tw / 2, 60), sub, font=f, fill=WHITE, anchor="mm")
            L = L.rotate(-3, Image.BICUBIC, expand=True); y += 30
            im.alpha_composite(L, (int(W / 2 - L.width / 2), int(y))); y += L.height + 70
        if cv.get("number"):
            f = _cv_fit(cv["number"].upper(), FBLACK, 230, W - 120)
            _cv_text(im, (W / 2, y + f.size * .45), cv["number"].upper(), f, YEL, blur=14); y += f.size
            if cv.get("caption"): _cv_text(im, (W / 2, y + 30), cv["caption"].upper(), _cv_fit(cv["caption"].upper(), FXB, 48, W - 120), WHITE, blur=8, off=(0, 4))
    _cv_header(im, badge)
    rgb = im.convert("RGB"); rgb.save(out, quality=93)
    th = os.path.splitext(out)[0] + "_thumb.jpg"; t = rgb.resize((180, 320), Image.LANCZOS); q = 90
    while True:
        t.save(th, quality=q)
        if os.path.getsize(th) < 190_000 or q < 40: break
        q -= 10
    return out, th

def build(scn_path, out, preview=None):
    S = json.load(open(scn_path)); base = os.path.dirname(os.path.abspath(scn_path))
    work = os.path.join(base, "work"); os.makedirs(work, exist_ok=True)
    scenes = [s for s in S["scenes"] if s.get("type") != "outro"]
    scenes.append({"type": "outro", "say": S.get("outro_say", OUTRO_SAY), "image": scenes[0].get("image"),
                   "video": scenes[0].get("video"), "video_start": scenes[0].get("video_start", 0)})
    imgs = {}
    for i, s in enumerate(scenes):
        if s.get("image"):
            p = s["image"] if os.path.isabs(s["image"]) else os.path.join(base, s["image"])
            imgs[i] = load(p)
    if S.get("voiceover"):
        vp = S["voiceover"] if os.path.isabs(S["voiceover"]) else os.path.join(base, S["voiceover"])
        vo = voice_from_file(scenes, vp, work)
    else:
        vo = voice(scenes, work)
    json.dump(vo, open(f"{work}/voice.json", "w"), ensure_ascii=False)
    c = Clip(scenes, vo, imgs); badge = S.get("badge", "ВИДЕО ДНЯ")
    c.vids = {}
    for i, s in enumerate(scenes):
        if s.get("video"):
            vp = s["video"] if os.path.isabs(s["video"]) else os.path.join(base, s["video"])
            c.vids[i] = VideoSrc(vp, s.get("video_start", 0), tuple(s.get("focus", (.5, .5))))
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
    if len(sys.argv) > 4 and sys.argv[4] == "cover":
        sp = sys.argv[1]
        print(make_cover(json.load(open(sp)), os.path.dirname(os.path.abspath(sp)), sys.argv[2]))
    elif len(sys.argv) > 4 and sys.argv[4] == "preview":
        print(build(sys.argv[1], sys.argv[2], preview=True))
    else:
        print(build(sys.argv[1], sys.argv[2]))
