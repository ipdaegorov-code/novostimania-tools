"""Поиск и скачивание свободных фото и видео. Результат — JSON-список кандидатов.

python3 -m nm.photos search --src pixabay   --q "oil pump jack"
python3 -m nm.photos search --src openverse --q "Kremlin Moscow"
python3 -m nm.photos search --src wikimedia --q "Konstantinovsky Palace"   [--video]
python3 -m nm.photos search --src nasa      --q "Valles Marineris"         [--video]
python3 -m nm.photos search --src pixabay   --q "ocean waves" --video
python3 -m nm.photos portrait --name "Сергей Лавров" --en "Sergey Lavrov"
python3 -m nm.photos get --url URL --out FILE      # скачать + проверить, что это JPEG/PNG/MP4

У каждого кандидата: url, w, h, license, credit ("" — указывать автора не нужно), title, tags.
Отбор по лицензиям уже сделан: только PD, CC0, CC BY, CC BY-SA; без ИИ-генерации, NC/ND, логотипов, карт и схем.
"""
import argparse, os, re, time, html, urllib.parse
from nm.common import http, out, die, load_state, save_state, UA

BAD_TAGS = ("ai generated", "generated", "illustration", "3d render", "ai-generated")
BAD_WORDS = ("logo", "map", "diagram", "screenshot", "icon", "scan", "annotated", "chart", "coat of arms", "seal of")
OK_LIC = ("cc0", "pdm", "public domain", "cc by", "cc-by", "by", "by-sa", "cc by-sa", "pd")


def _strip(s):
    return html.unescape(re.sub("<[^>]+>", "", s or "")).strip()


def _wiki_wait():
    st = load_state(); last = st.get("wiki_last", 0); d = time.time() - last
    if d < 10: time.sleep(10 - d)
    st["wiki_last"] = time.time(); save_state(st)


def _wiki(params):
    q = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(dict(params, format="json"))
    for _ in range(6):
        _wiki_wait(); r = http(q)
        if "_raw" not in r: return r
        time.sleep(45)
    die("Wikimedia не отвечает (лимит запросов)")


def pixabay(q, video=False):
    key = os.environ.get("PIXABAY_KEY")
    if not key: return {"skip": "нет PIXABAY_KEY — источник пропущен"}
    base = "https://pixabay.com/api/videos/" if video else "https://pixabay.com/api/"
    p = {"key": key, "q": q, "safesearch": "true", "per_page": 20}
    if not video: p.update(image_type="photo", min_width=1080)
    r = http(base + "?" + urllib.parse.urlencode(p)); res = []
    for h in r.get("hits", []):
        tags = h.get("tags", "")
        if any(b in tags.lower() for b in BAD_TAGS): continue
        if video:
            lg = h["videos"].get("large") or {}
            v = lg if lg.get("url") and 0 < (lg.get("width") or 0) <= 1920 else h["videos"].get("medium")
            if not v or not v.get("url"): continue
            res.append({"url": v["url"], "w": v.get("width"), "h": v.get("height"), "duration": h.get("duration"),
                        "license": "Pixabay", "credit": "", "tags": tags, "title": tags})
        else:
            res.append({"url": h["largeImageURL"], "w": h.get("imageWidth"), "h": h.get("imageHeight"),
                        "license": "Pixabay", "credit": "", "tags": tags, "title": tags})
    return res


def openverse(q):
    r = http("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({"q": q, "license_type": "commercial", "page_size": 20}))
    res = []
    for h in r.get("results", []):
        lic = (h.get("license") or "").lower()
        if lic not in ("cc0", "pdm", "by", "by-sa") or (h.get("width") or 0) < 1000: continue
        t = (h.get("title") or "").lower()
        if any(b in t for b in BAD_WORDS + BAD_TAGS): continue
        cr = ""
        if lic in ("by", "by-sa"):
            cr = f"Фото: {h.get('creator') or 'автор'}, CC {lic.upper()} {h.get('license_version') or ''}".strip()
        res.append({"url": h["url"], "w": h.get("width"), "h": h.get("height"), "license": lic, "credit": cr, "title": h.get("title")})
    return res


def wikimedia(q, video=False, min_side=1000):
    r = _wiki({"action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 20,
               "gsrsearch": f"{q} filetype:{'video' if video else 'bitmap'}", "prop": "imageinfo",
               "iiprop": "url|extmetadata|size", "iiurlwidth": 1280})
    res = []
    for p in r.get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]; md = ii.get("extmetadata", {})
        lic = _strip(md.get("LicenseShortName", {}).get("value", "")); ll = lic.lower()
        if any(x in ll for x in ("nc", "nd", "fair use")) or not any(x in ll for x in OK_LIC): continue
        title = p.get("title", ""); tl = title.lower()
        if any(b in tl for b in BAD_WORDS) or tl.endswith(".pdf"): continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if not video and min(w, h) < min_side: continue
        url = ii.get("url") if video else (ii.get("thumburl") or ii.get("url"))
        url = url.replace("https://thumb.wikimedia.org/", "https://upload.wikimedia.org/").split("?")[0]
        art = _strip(md.get("Artist", {}).get("value", ""))[:30]
        need = ll.startswith("cc by") or ll.startswith("cc-by")
        res.append({"url": url, "w": w, "h": h, "license": lic, "title": title,
                    "credit": f"Фото: {art}, {lic}" if need else ""})
    return res


def nasa(q, video=False):
    r = http("https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": q, "media_type": "video" if video else "image"}))
    res = []
    for it in r.get("collection", {}).get("items", [])[:20]:
        d = (it.get("data") or [{}])[0]; nid = d.get("nasa_id")
        if not nid: continue
        e = urllib.parse.quote(nid)
        if video:
            a = http(f"https://images-api.nasa.gov/asset/{e}")
            hrefs = [x["href"] for x in a.get("collection", {}).get("items", [])]
            mp4 = next((h for h in hrefs if h.endswith("~medium.mp4")), None) or next((h for h in hrefs if h.endswith(".mp4")), None)
            if not mp4: continue
            url = mp4.replace("http://", "https://").replace(" ", "%20")
        else:
            url = f"https://images-assets.nasa.gov/image/{e}/{e}~large.jpg"
        res.append({"url": url, "license": "NASA (общественное достояние)", "credit": "", "title": d.get("title"),
                    "alt": [url.replace("~large.jpg", "~orig.jpg"), url.replace("~large.jpg", "~medium.jpg")] if not video else []})
    return res


def portrait(name, en):
    res = []
    for q in (f"{en} official portrait", f"{en} 2025", f"{en}"):
        for c in wikimedia(q, min_side=300):
            t = c["title"].lower()
            if all(part.lower() in t for part in en.split()[-1:]):
                res.append(c)
        if res: break
    return res


def get(url, path):
    data = http(url, raw=True, timeout=180)
    if len(data) < 2000: die(f"файл слишком маленький или не загрузился: {url}")
    head = data[:12]
    kind = "jpeg" if head[:3] == b"\xff\xd8\xff" else "png" if head[:8] == b"\x89PNG\r\n\x1a\n" else \
        "mp4" if b"ftyp" in data[:16] else "webm" if head[:4] == b"\x1a\x45\xdf\xa3" else None
    if not kind: die(f"это не картинка и не видео (возможно, HTML или лимит). Подожди 45 секунд и повтори: {url}")
    with open(path, "wb") as f: f.write(data)
    info = {"ok": True, "file": path, "kind": kind, "bytes": len(data)}
    if kind in ("jpeg", "png"):
        from PIL import Image
        with Image.open(path) as im: info.update(w=im.width, h=im.height)
    return info


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("search"); a.add_argument("--src", required=True, choices=["pixabay", "openverse", "wikimedia", "nasa"])
    a.add_argument("--q", required=True); a.add_argument("--video", action="store_true")
    a = sp.add_parser("portrait"); a.add_argument("--name", required=True); a.add_argument("--en", required=True)
    a = sp.add_parser("get"); a.add_argument("--url", required=True); a.add_argument("--out", required=True)
    g = ap.parse_args()
    if g.cmd == "search":
        f = {"pixabay": lambda: pixabay(g.q, g.video), "openverse": lambda: openverse(g.q),
             "wikimedia": lambda: wikimedia(g.q, g.video), "nasa": lambda: nasa(g.q, g.video)}[g.src]
        r = f(); out(r if isinstance(r, dict) else {"ok": True, "count": len(r), "items": r})
    elif g.cmd == "portrait":
        r = portrait(g.name, g.en); out({"ok": True, "count": len(r), "items": r})
    else:
        out(get(g.url, g.out))


if __name__ == "__main__":
    main()
