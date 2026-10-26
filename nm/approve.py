"""Диалог с владельцем в Telegram-боте: превью и ожидание ответов.

python3 -m nm.approve start                                  # запомнить момент T (ответы раньше — игнор)
python3 -m nm.approve preview --photo P --text post.txt --label "🖼 09:00 · Политика — предложение" [--opinion]
python3 -m nm.approve wait --until UNIX|ЧЧ:ММ [--max 480]    # ждёт новые сообщения владельца (опрос раз в 20 с)
python3 -m nm.approve video-preview --video V --cover C --caption "…"

wait возвращает {"messages":[{"text":…, "photo":путь или null, "date":…}], "deadline": true/false}
— сразу, как только пришло хоть одно сообщение; иначе по истечении --max секунд или срока --until.
Фото владельца скачиваются в ./inbox/. Offset хранится в ~/.nm_state.json и не сбрасывается между вызовами.
"""
import argparse, os, time
from nm.common import cfg, http, out, die, need, read_text, load_state, save_state
from nm import publish

C = cfg()
OWNER = C["telegram"]["owner_id"]
QUESTION = ("Выкладываем? «да» · своё фото · команда («наложи флаги РФ и США», «сделай три флага», "
            "«замени фон на …», «сделай карточку», «канва <что нарисовать>») · «стоп» — отменить")


def api(method, **params):
    import urllib.parse
    q = urllib.parse.urlencode(params)
    return http(f"https://api.telegram.org/bot{need('TG_TOKEN')}/{method}?{q}", timeout=40)


def start():
    st = load_state(); st["T"] = int(time.time()); save_state(st); return st["T"]


def _download(file_id):
    r = api("getFile", file_id=file_id)
    fp = r.get("result", {}).get("file_path")
    if not fp: return None
    data = http(f"https://api.telegram.org/file/bot{need('TG_TOKEN')}/{fp}", raw=True, timeout=120)
    os.makedirs("inbox", exist_ok=True)
    path = os.path.abspath(os.path.join("inbox", f"{int(time.time())}_{os.path.basename(fp)}"))
    with open(path, "wb") as f: f.write(data)
    return path


def poll_once():
    st = load_state(); T = st.get("T", 0); params = {"timeout": 0}
    if "offset" in st: params["offset"] = st["offset"]
    r = api("getUpdates", **params); msgs = []
    for u in r.get("result", []):
        st["offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        if m.get("chat", {}).get("id") != OWNER or m.get("date", 0) <= T: continue
        photo = None
        if m.get("photo"): photo = _download(m["photo"][-1]["file_id"])
        elif (m.get("document") or {}).get("mime_type", "").startswith("image/"): photo = _download(m["document"]["file_id"])
        msgs.append({"text": (m.get("text") or m.get("caption") or "").strip(), "photo": photo, "date": m["date"]})
    save_state(st)
    return msgs


def until_ts(v):
    """--until: unix-время или ЧЧ:ММ по Москве (ближайшее такое время, не раньше чем 12 ч назад)."""
    import argparse, datetime
    from nm.common import now
    if v.isdigit():
        return int(v)
    try:
        h, m = map(int, v.split(":"))
        t = now().replace(hour=h, minute=m, second=0, microsecond=0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--until: нужно unix-время или ЧЧ:ММ, а не {v!r}")
    if (now() - t).total_seconds() > 12 * 3600:
        t += datetime.timedelta(days=1)
    return int(t.timestamp())


def wait(until, maxs):
    end = min(until, time.time() + maxs)
    while True:
        msgs = poll_once()
        if msgs: return {"ok": True, "messages": msgs, "deadline": time.time() >= until}
        if time.time() >= end: return {"ok": True, "messages": [], "deadline": time.time() >= until}
        time.sleep(min(20, max(1, end - time.time())))


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("start")
    a = sp.add_parser("preview"); a.add_argument("--photo", required=True); a.add_argument("--text", required=True)
    a.add_argument("--label", required=True); a.add_argument("--opinion", action="store_true")
    a = sp.add_parser("wait"); a.add_argument("--until", type=until_ts, required=True); a.add_argument("--max", type=int, default=480)
    a = sp.add_parser("video-preview"); a.add_argument("--video", required=True); a.add_argument("--cover", required=True); a.add_argument("--caption", required=True)
    g = ap.parse_args()
    if g.cmd == "start": out({"ok": True, "T": start()})
    elif g.cmd == "preview":
        publish.tg("sendPhoto", {"chat_id": OWNER, "caption": g.label}, {"photo": g.photo})
        q = QUESTION + ("\n💬 И что думаешь? Напиши мнение — добавлю в пост" if g.opinion else "")
        publish.tg("sendMessage", {"chat_id": OWNER, "text": read_text(g.text) + "\n\n— — —\n" + q})
        out({"ok": True})
    elif g.cmd == "wait": out(wait(g.until, g.max))
    elif g.cmd == "video-preview":
        publish.tg("sendPhoto", {"chat_id": OWNER, "caption": "🖼 Обложка для клипа"}, {"photo": g.cover})
        publish.tg("sendVideo", {"chat_id": OWNER, "caption": g.caption, "width": 1080, "height": 1920, "supports_streaming": "true"}, {"video": g.video})
        out({"ok": True})


if __name__ == "__main__":
    main()
