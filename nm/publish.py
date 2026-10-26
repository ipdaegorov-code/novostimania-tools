"""Публикация: Telegram, MAX, ВК. Ключи берутся из окружения и нигде не печатаются.

Текст поста пишется ОДИН раз в файл с хэштегами без суффикса (#Политика).
Для ВК суффикс @newsobsession добавляется автоматически.

python3 -m nm.publish vk        --text post.txt --at UNIX [--photo post.jpg]
    # отложенный пост в ВК (214 = уже стоит — ок). С --photo и NM_GATE_URL/NM_GATE_KEY пост с картинкой
    # ставит шлюз на сервере (server/vkgate.py); если шлюз недоступен — только текст через VK_TOKEN,
    # в ответе "photo": false и "gate_error".
python3 -m nm.publish tg-photo  --to channel|owner --photo P --text post.txt
python3 -m nm.publish tg-msg    --to owner --text "строка"  |  --text-file F
python3 -m nm.publish tg-video  --to channel|owner --video V --text F [--thumb T]
python3 -m nm.publish tg-doc    --to owner --file F --caption "…"
python3 -m nm.publish max-photo --photo P --text post.txt
python3 -m nm.publish max-video --video V --text post.txt
python3 -m nm.publish max-recent [--count 50] [--days 3]             # первые строки постов MAX за N дней
python3 -m nm.publish check                                          # каких ключей не хватает
"""
import argparse, base64, json, os, re, time, datetime
from nm.common import cfg, http, multipart, out, die, need, read_text, now, tz, scrub

C = cfg()


def chat(to):
    return C["telegram"]["channel_id"] if to == "channel" else C["telegram"]["owner_id"]


def tg(method, fields, files=None):
    url = f"https://api.telegram.org/bot{need('TG_TOKEN')}/{method}"
    for attempt in range(2):
        r = multipart(url, {k: str(v) for k, v in fields.items()}, files or {})
        if r.get("ok"): return r
        desc = r.get("description", str(r))
        if "too long" in desc.lower():
            die(f"caption is too long ({len(fields.get('caption',''))} знаков) — сократи текст до 1000 знаков и повтори")
        if attempt == 0: time.sleep(3)
    die(f"Telegram {method}: {desc}")


def vk_text(text):
    suf = C["vk"]["hashtag_suffix"]
    return re.sub(r"#(\w+)(?![\w@])", lambda m: f"#{m.group(1)}{suf}", text)


def vk_gate(text, at, photo):
    """Пост с картинкой через шлюз на сервере. Возвращает ответ или None с причиной."""
    url, key = os.environ.get("NM_GATE_URL"), os.environ.get("NM_GATE_KEY")
    if not (url and key): return None, "нет NM_GATE_URL/NM_GATE_KEY"
    with open(photo, "rb") as f:
        body = json.dumps({"text": vk_text(text), "at": at, "photo_b64": base64.b64encode(f.read()).decode()}).encode()
    for attempt in range(2):
        r = http(url.rstrip("/") + "/vk/post", data=body, method="POST", timeout=180,
                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        if r.get("ok"): return r, None
        if attempt == 0: time.sleep(3)
    return None, r.get("error") or str(r)[:200]


def vk(text, at, photo=None):
    gate_error = None
    if photo:
        r, gate_error = vk_gate(text, at, photo)
        if r: return r
    p = {"owner_id": -C["vk"]["group_id"], "from_group": 1, "message": vk_text(text), "publish_date": at,
         "access_token": need("VK_TOKEN"), "v": C["vk"]["api_version"]}
    for attempt in range(2):
        r = http("https://api.vk.com/method/wall.post", data=p)
        if "response" in r: return {"ok": True, "post_id": r["response"]["post_id"], "photo": False, "gate_error": gate_error}
        e = r.get("error", {})
        if e.get("error_code") == 214: return {"ok": True, "already": True, "note": "на это время пост в ВК уже стоит — не дублирую"}
        if attempt == 0: time.sleep(3)
    die(f"ВК: {e.get('error_code')} {e.get('error_msg')}")


def max_hdr(ct=None):
    h = {"Authorization": need("MAX_TOKEN")}
    if ct: h["Content-Type"] = ct
    return h


def max_upload(path, kind):
    base = C["max"]["base"]
    r = http(f"{base}/uploads?type={kind}", data=b"", headers=max_hdr(), method="POST")
    if "url" not in r: die(f"MAX uploads: {r}")
    up = multipart(r["url"], {}, {"data": path}, timeout=600)
    if kind == "image": return up
    return {"token": r.get("token") or up.get("token")}


def max_send(text, payload, kind):
    base = C["max"]["base"]
    body = json.dumps({"text": text, "attachments": [{"type": kind, "payload": payload}]}, ensure_ascii=False).encode()
    tries = 10 if kind == "video" else 5
    for i in range(tries):
        r = http(f"{base}/messages?chat_id={C['max']['channel_id']}", data=body, headers=max_hdr("application/json"), method="POST")
        mid = r.get("message", {}).get("body", {}).get("mid")
        if mid: return {"ok": True, "mid": mid}
        if "attachment.not.ready" in json.dumps(r):
            time.sleep(3 if kind == "video" else 2); continue
        break
    die(f"MAX messages: {r}")


def max_recent(count=50, days=3):
    base = C["max"]["base"]
    r = http(f"{base}/messages?chat_id={C['max']['channel_id']}&count={count}", headers=max_hdr())
    today = now().date(); since = today - datetime.timedelta(days=days - 1); res = []
    for m in r.get("messages", []):
        ts = m.get("timestamp", 0) / 1000
        d = datetime.datetime.fromtimestamp(ts, tz())
        if d.date() < since: continue
        txt = m.get("body", {}).get("text", "") or ""
        att = [a.get("type") for a in m.get("body", {}).get("attachments", []) or []]
        res.append({"_ts": ts, "date": d.strftime("%d.%m"), "time": d.strftime("%H:%M"), "today": d.date() == today, "first_line": txt.split("\n")[0], "has_video": "video" in att})
    res.sort(key=lambda x: x["_ts"])
    for x in res: x.pop("_ts")
    return {"ok": True, "days": days, "posts": res}


def check():
    miss = [v for v in ("VK_TOKEN", "TG_TOKEN", "MAX_TOKEN") if not os.environ.get(v)]
    gate = bool(os.environ.get("NM_GATE_URL") and os.environ.get("NM_GATE_KEY"))
    return {"ok": not miss, "missing": miss, "pixabay": bool(os.environ.get("PIXABAY_KEY")), "vk_gate": gate}


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("vk"); a.add_argument("--text", required=True); a.add_argument("--at", type=int, required=True); a.add_argument("--photo")
    a = sp.add_parser("tg-photo"); a.add_argument("--to", required=True); a.add_argument("--photo", required=True); a.add_argument("--text", required=True)
    a = sp.add_parser("tg-msg"); a.add_argument("--to", default="owner"); a.add_argument("--text"); a.add_argument("--text-file")
    a = sp.add_parser("tg-video"); a.add_argument("--to", required=True); a.add_argument("--video", required=True)
    a.add_argument("--text", required=True); a.add_argument("--thumb")
    a = sp.add_parser("tg-doc"); a.add_argument("--to", default="owner"); a.add_argument("--file", required=True); a.add_argument("--caption", default="")
    a = sp.add_parser("max-photo"); a.add_argument("--photo", required=True); a.add_argument("--text", required=True)
    a = sp.add_parser("max-video"); a.add_argument("--video", required=True); a.add_argument("--text", required=True)
    a = sp.add_parser("max-recent"); a.add_argument("--count", type=int, default=50); a.add_argument("--days", type=int, default=3)
    sp.add_parser("check")
    g = ap.parse_args()
    if g.cmd == "vk": out(vk(read_text(g.text), g.at, g.photo))
    elif g.cmd == "tg-photo":
        r = tg("sendPhoto", {"chat_id": chat(g.to), "caption": read_text(g.text)}, {"photo": g.photo})
        out({"ok": True, "message_id": r["result"]["message_id"]})
    elif g.cmd == "tg-msg":
        t = g.text if g.text else read_text(g.text_file)
        r = tg("sendMessage", {"chat_id": chat(g.to), "text": t}); out({"ok": True, "message_id": r["result"]["message_id"]})
    elif g.cmd == "tg-video":
        f = {"video": g.video}
        if g.thumb: f["thumbnail"] = g.thumb
        r = tg("sendVideo", {"chat_id": chat(g.to), "caption": read_text(g.text), "width": 1080, "height": 1920, "supports_streaming": "true"}, f)
        out({"ok": True, "message_id": r["result"]["message_id"]})
    elif g.cmd == "tg-doc":
        r = tg("sendDocument", {"chat_id": chat(g.to), "caption": g.caption}, {"document": g.file}); out({"ok": True})
    elif g.cmd == "max-photo": out(max_send(read_text(g.text), max_upload(g.photo, "image"), "image"))
    elif g.cmd == "max-video": out(max_send(read_text(g.text), max_upload(g.video, "video"), "video"))
    elif g.cmd == "max-recent": out(max_recent(g.count, g.days))
    elif g.cmd == "check": out(check())


if __name__ == "__main__":
    main()
