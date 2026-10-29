"""Лента российских СМИ из RSS: склеивает одну новость от разных изданий, считает источники.

python3 -m nm.feeds top [--hours 12 | --today] [--min 2] [--limit 12] [--q "ставка"]
python3 -m nm.feeds image --link ARTICLE_URL --img RSS_IMAGE   # то же фото в самом крупном размере со страницы статьи

top: список событий от самых широко освещённых. У события: title, n (число изданий),
last (время последней публикации), image (лучшее фото из ленты или ""), summary, items — до 4 изданий
(сначала с фото): src, title, link, time, image. Ленты, которые не открылись, — в failed.
"""
import argparse, datetime, email.utils, html, io, re, urllib.parse, xml.etree.ElementTree as ET
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from nm.common import http, out, die, cfg, tz, now

MEDIA_NS = "{http://search.yahoo.com/mrss/}"
STOP = set("в во на по за из от до для при без над под про об о и а но или что как это его ее её их не ни же ли бы уже еще ещё".split())


def _strip(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", s or ""))).strip()


def _when(s):
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def _image(it):
    for e in it.iter():
        tag = e.tag.split("}")[-1]
        url = e.get("url") or ""
        if tag == "enclosure" and (e.get("type", "").startswith("image") or re.search(r"\.(jpe?g|png|webp)", url, re.I)):
            return url
        if e.tag in (MEDIA_NS + "content", MEDIA_NS + "thumbnail") and url:
            return url
    return ""


def fetch(src, url):
    try:
        root = ET.fromstring(http(url, timeout=20, raw=True))
    except Exception:  # лента не открылась или отдала не XML — попадёт в failed
        return src, None
    items = []
    for it in root.iter("item"):
        title = _strip(it.findtext("title"))
        t = _when(it.findtext("pubDate") or "")
        if not title or not t:
            continue
        items.append({"src": src, "title": title, "link": (it.findtext("link") or "").strip(),
                      "time": t, "summary": _strip(it.findtext("description"))[:160], "image": _image(it)})
    return src, items


def _words(title):
    # грубая основа слова: первые 5 букв — склеивает «ставку/ставки», «Путин/Путина»
    return {w[:5] for w in re.findall(r"[а-яёa-z0-9]+", title.lower()) if len(w) > 2 and w not in STOP}


def cluster(items, thr=0.3):
    groups = []
    for it in sorted(items, key=lambda x: x["time"], reverse=True):
        w = _words(it["title"])
        best, score = None, 0
        for g in groups:
            j = len(w & g["w"]) / (len(w | g["w"]) or 1)
            if j > score:
                best, score = g, j
        if best and score >= thr:
            best["items"].append(it)
            best["w"] |= w
        else:
            groups.append({"w": set(w), "items": [it]})
    return groups


def top(hours, min_src, limit, q, today=False):
    since = now().replace(hour=0, minute=0, second=0, microsecond=0) if today else now() - datetime.timedelta(hours=hours)
    feeds = cfg()["feeds"]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda kv: fetch(*kv), feeds.items()))
    failed = [s for s, items in res if not items]
    items = [i for _, its in res if its for i in its if i["time"] >= since]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i["title"] + " " + i["summary"]).lower()]
    events = []
    for g in cluster(items):
        by_src = {}
        for i in g["items"]:
            by_src.setdefault(i["src"], i)
        if len(by_src) < min_src:
            continue
        its = sorted(by_src.values(), key=lambda x: x["time"])
        img = next((i["image"] for i in its if i["image"] and i["src"] != "tass"), "") or next((i["image"] for i in its if i["image"]), "")
        events.append({"title": its[0]["title"], "n": len(its), "last": max(i["time"] for i in its), "image": img,
                       "summary": next((i["summary"] for i in its if i["summary"]), ""),
                       "items": [{k: v for k, v in dict(i, time=i["time"].astimezone(tz()).strftime("%d.%m %H:%M")).items() if k != "summary"}
                                 for i in sorted(its, key=lambda x: (not x["image"], x["src"] == "tass"))[:4]]})
    events.sort(key=lambda e: (e["n"], e["last"]), reverse=True)
    for e in events:
        e["last"] = e["last"].astimezone(tz()).strftime("%d.%m %H:%M")
    out({"ok": True, "events": events[:limit], "total": len(events), "failed": failed})


SKIP_IMG = re.compile(r"share|sharing|social|owl_detail|logo|icon|avatar|dummy", re.I)


def _stems(img):
    """Опознавательные куски адреса фото: длинные числа и имя папки (у CDN они общие для всех размеров)."""
    path = urllib.parse.urlparse(img).path
    st = {d for d in re.findall(r"\d{6,}", path) if not re.fullmatch(r"20\d{6}", d)}
    parts = path.strip("/").split("/")
    if len(parts) > 1 and len(parts[-2]) >= 5 and not parts[-2].isdigit():
        st.add(parts[-2])
    return st


def _size(url):
    try:
        im = Image.open(io.BytesIO(http(url, raw=True, timeout=20)))
        return im.size[0] * im.size[1], im.size
    except Exception:
        return 0, None


def image(link, img):
    """Крупный вариант фото из RSS. Карточки для соцсетей (с заголовком и логотипом поверх) не берём."""
    best = (_size(img) + (img,)) if img else (0, None, "")
    stems = _stems(img) if img else set()
    if stems:
        try:
            page = http(link, timeout=20, raw=True).decode("utf-8", "replace")
        except Exception:
            page = ""
        urls = set(re.findall(r"https?://[^\"'\s()<>,]+?\.(?:jpe?g|png)", page, re.I))
        cand = [u for u in urls if any(s in u for s in stems) and not SKIP_IMG.search(u)][:8]
        for u in cand:
            area, size = _size(u)
            if area > best[0]:
                best = (area, size, u)
    if not best[1]:
        die("фото не найдено")
    out({"ok": True, "url": best[2], "w": best[1][0], "h": best[1][1]})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("top")
    t.add_argument("--hours", type=float, default=12)
    t.add_argument("--today", action="store_true", help="с 00:00 по Москве")
    t.add_argument("--min", type=int, default=2)
    t.add_argument("--limit", type=int, default=12)
    t.add_argument("--q", default="")
    i = sp.add_parser("image")
    i.add_argument("--link", required=True)
    i.add_argument("--img", default="")
    a = ap.parse_args()
    top(a.hours, a.min, a.limit, a.q, a.today) if a.cmd == "top" else image(a.link, a.img)
