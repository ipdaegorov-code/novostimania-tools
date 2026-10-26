"""Общее: конфиг, время, ключи, безопасный вывод, HTTP."""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "NovostimaniyaBot/1.0 (https://vk.com/newsobsession)"
SECRET_VARS = ("VK_TOKEN", "TG_TOKEN", "MAX_TOKEN", "PIXABAY_KEY", "NM_GATE_KEY")
STATE = os.path.expanduser("~/.nm_state.json")


def cfg():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def tz():
    return ZoneInfo(cfg()["tz"])


def now():
    return datetime.datetime.now(tz())


def scrub(s):
    """Убирает значения ключей из любого текста (ошибки, ответы API)."""
    s = str(s)
    for v in SECRET_VARS:
        val = os.environ.get(v)
        if val:
            s = s.replace(val, f"<{v}>")
    return s


def die(msg, code=1):
    print(json.dumps({"ok": False, "error": scrub(msg)}, ensure_ascii=False))
    sys.exit(code)


def out(obj):
    print(scrub(json.dumps(obj, ensure_ascii=False)))


def need(var):
    v = os.environ.get(var)
    if not v:
        die(f"нет переменной окружения {var}")
    return v


def http(url, data=None, headers=None, method=None, timeout=60, raw=False):
    """Простой HTTP. data: dict -> form-urlencoded, bytes -> как есть."""
    h = {"User-Agent": UA}
    h.update(headers or {})
    if isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        body = e.read()
    if raw:
        return body
    try:
        return json.loads(body)
    except Exception:
        return {"_raw": body[:500].decode("utf-8", "replace")}


def multipart(url, fields, files, headers=None, timeout=300):
    """POST multipart/form-data. files: {name: path}."""
    import uuid, mimetypes
    b = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, p in files.items():
        ct = mimetypes.guess_type(p)[0] or "application/octet-stream"
        with open(p, "rb") as f:
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{os.path.basename(p)}"\r\nContent-Type: {ct}\r\n\r\n'.encode() + f.read() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    h = {"Content-Type": f"multipart/form-data; boundary={b}"}
    h.update(headers or {})
    return http(url, data=b"".join(parts), headers=h, timeout=timeout)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f)


def slot_for(when=None, min_lead=20):
    """Ближайший слот, до которого осталось >= min_lead минут."""
    when = when or now()
    for s in cfg()["slots"]:
        hh, mm = map(int, s["time"].split(":"))
        t = when.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if (t - when).total_seconds() >= min_lead * 60:
            return s, t
    return None, None


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()
