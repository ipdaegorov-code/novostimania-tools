"""vkgate — шлюз ВК на сервере AEZA: хранит ключ VK ID, сам его продлевает,
загружает фото и ставит отложенные посты в группу. Только стандартная библиотека Python.

Настройки — из окружения (файл /etc/nmgate.env):
  VK_APP_ID      ID приложения VK ID
  VK_GROUP_ID    ID группы (без минуса)
  NM_GATE_KEY    общий секрет с ботом (заголовок Authorization: Bearer …)
  NM_GATE_DIR    где хранить ключи (по умолчанию /var/lib/nmgate)
  NM_GATE_PORT   порт (по умолчанию 8787, слушает только 127.0.0.1)

python3 vkgate.py login-url          # ссылка для входа через VK ID
python3 vkgate.py login 'АДРЕС'      # адрес из браузера после входа (…blank.html?code=…)
python3 vkgate.py check              # ключ жив? права на группу есть?
python3 vkgate.py serve              # HTTP-сервис (запускает systemd)

HTTP:
  GET  /health                       {"ok", "login": true|false, "expires_in"}
  POST /vk/post  (Bearer)            {"text", "at": unix, "photo_b64"?: jpg в base64}
                                     → {"ok": true, "post_id", "photo": true|false} | {"ok": true, "already": true}
"""
import base64, hashlib, hmac, json, os, secrets, sys, threading, time, uuid
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_ID = os.environ.get("VK_APP_ID", "")
GROUP_ID = int(os.environ.get("VK_GROUP_ID", "0") or 0)
KEY = os.environ.get("NM_GATE_KEY", "")
DIR = os.environ.get("NM_GATE_DIR", "/var/lib/nmgate")
PORT = int(os.environ.get("NM_GATE_PORT", "8787"))
REDIRECT = "https://oauth.vk.com/blank.html"
SCOPE = "wall photos video groups"
API_V = "5.199"
TOKEN_FILE = os.path.join(DIR, "token.json")
LOGIN_FILE = os.path.join(DIR, "login.json")
LOCK = threading.Lock()


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save(path, obj):
    os.makedirs(DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def post(url, data=None, body=None, headers=None, timeout=60, tries=3):
    """POST с повторами при сетевых сбоях (ВК из-за рубежа иногда зависает на TLS).
    tries=1 — для одноразовых запросов (код входа, ключ обновления): повтор может их сжечь."""
    h = {"User-Agent": "NovostimaniyaGate/1.0"}
    h.update(headers or {})
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    for i in range(tries):
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            raw = e.read(); break
        except (urllib.error.URLError, OSError) as e:
            err = str(getattr(e, "reason", e))
            if i + 1 < tries: log(f"сеть ({url.split('?')[0]}): {err}, повтор"); time.sleep(5 * (i + 1))
    else:
        return {"error": "network", "error_description": err}
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:300].decode("utf-8", "replace")}


# ---------- VK ID: вход и продление ----------

def login_url():
    if not APP_ID: sys.exit("нет VK_APP_ID")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    save(LOGIN_FILE, {"verifier": verifier, "state": state, "t": time.time()})
    q = {"response_type": "code", "client_id": APP_ID, "redirect_uri": REDIRECT, "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256", "scope": SCOPE}
    return "https://id.vk.com/authorize?" + urllib.parse.urlencode(q)


def login(addr):
    lg = load(LOGIN_FILE)
    if not lg: sys.exit("сначала: python3 vkgate.py login-url")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(addr.strip()).query)
    if "payload" in q:  # иногда VK ID кладёт всё в один JSON-параметр
        q = {k: [str(v)] for k, v in json.loads(q["payload"][0]).items()}
    code, device, state = (q.get(k, [""])[0] for k in ("code", "device_id", "state"))
    if not code or not device: sys.exit("в адресе нет code или device_id — скопируйте адрес целиком")
    if state != lg["state"]: sys.exit("state не совпадает — получите новую ссылку: login-url")
    r = post("https://id.vk.com/oauth2/auth", {
        "grant_type": "authorization_code", "code_verifier": lg["verifier"], "redirect_uri": REDIRECT,
        "code": code, "client_id": APP_ID, "device_id": device, "state": state}, tries=1)
    if r.get("error") == "network":
        sys.exit(f"нет связи с id.vk.com ({r['error_description']}) — повторите эту же команду (код живёт 10 минут)")
    if "access_token" not in r: sys.exit(f"VK ID отказал: {r.get('error')} {r.get('error_description', '')}")
    store(r, device)
    os.remove(LOGIN_FILE)
    print(f"вход выполнен, user_id={r.get('user_id')}, права: {r.get('scope')}")


def store(r, device):
    save(TOKEN_FILE, {"access_token": r["access_token"], "refresh_token": r["refresh_token"],
                      "expires_at": time.time() + int(r.get("expires_in", 3600)),
                      "device_id": device, "user_id": r.get("user_id"), "need_login": False})


def refresh(force=False):
    """Продлевает ключ, если до конца меньше 15 минут. Ключ обновления при этом меняется — пишем сразу."""
    with LOCK:
        t = load(TOKEN_FILE)
        if not t or t.get("need_login"): return t
        if not force and t["expires_at"] - time.time() > 900: return t
        r = post("https://id.vk.com/oauth2/auth", {
            "grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": APP_ID,
            "device_id": t["device_id"], "state": secrets.token_urlsafe(16)}, tries=1)
        if "access_token" in r:
            store(r, t["device_id"]); log("ключ продлён")
            return load(TOKEN_FILE)
        log("продление не удалось:", r.get("error"), r.get("error_description", ""))
        if r.get("error") in ("invalid_grant", "invalid_request", "invalid_client"):
            t["need_login"] = True; save(TOKEN_FILE, t)
        return t


def token():
    t = refresh()
    if not t or t.get("need_login") or t["expires_at"] < time.time():
        raise GateError("нужен повторный вход на сервере: vkgate.py login-url")
    return t["access_token"]


def keepalive():
    while True:
        try: refresh()
        except Exception as e: log("keepalive:", e)
        time.sleep(600)


# ---------- ВК API ----------

class GateError(Exception):
    pass


def api(method, **p):
    p.update(access_token=token(), v=API_V)
    r = post(f"https://api.vk.com/method/{method}", p)
    if "response" in r: return r["response"]
    e = r.get("error", {})
    raise GateError(f"{method}: {e.get('error_code')} {e.get('error_msg')}", e.get("error_code"))


def upload_photo(jpg):
    srv = api("photos.getWallUploadServer", group_id=GROUP_ID)
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="post.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n").encode() + jpg + f"\r\n--{b}--\r\n".encode()
    up = post(srv["upload_url"], body=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"}, timeout=120)
    if not up.get("photo") or up.get("photo") == "[]": raise GateError(f"загрузка фото: {up}")
    saved = api("photos.saveWallPhoto", group_id=GROUP_ID, server=up["server"], photo=up["photo"], hash=up["hash"])
    return f"photo{saved[0]['owner_id']}_{saved[0]['id']}"


def wall_post(text, at, jpg=None):
    att = upload_photo(jpg) if jpg else ""
    p = {"owner_id": -GROUP_ID, "from_group": 1, "message": text, "publish_date": int(at)}
    if att: p["attachments"] = att
    try:
        r = api("wall.post", **p)
    except GateError as e:
        if len(e.args) > 1 and e.args[1] == 214:
            return {"ok": True, "already": True, "note": "на это время пост в ВК уже стоит — не дублирую"}
        raise
    return {"ok": True, "post_id": r["post_id"], "photo": bool(att)}


def check():
    t = refresh(force=True)
    if not t: return {"ok": False, "error": "входа ещё не было: login-url"}
    if t.get("need_login"): return {"ok": False, "error": "ключ обновления не принят — нужен повторный вход"}
    me = api("users.get")[0]
    g = api("groups.getById", group_id=GROUP_ID, fields="can_post")
    g = (g.get("groups") or [{}])[0] if isinstance(g, dict) else g[0]
    srv = api("photos.getWallUploadServer", group_id=GROUP_ID)
    return {"ok": True, "user": f"{me['first_name']} {me['last_name']}", "group": g.get("name"),
            "admin": bool(g.get("is_admin")), "photo_upload": bool(srv.get("upload_url")),
            "expires_in": int(t["expires_at"] - time.time())}


# ---------- HTTP ----------

class H(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path != "/health": return self.reply(404, {"ok": False})
        t = load(TOKEN_FILE)
        ok = bool(t) and not t.get("need_login")
        self.reply(200, {"ok": True, "login": ok, "expires_in": int(t["expires_at"] - time.time()) if ok else 0})

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        if not KEY or not hmac.compare_digest(auth, f"Bearer {KEY}"):
            return self.reply(401, {"ok": False, "error": "нет доступа"})
        if self.path != "/vk/post": return self.reply(404, {"ok": False})
        n = int(self.headers.get("Content-Length", "0"))
        if n > 20_000_000: return self.reply(413, {"ok": False, "error": "слишком большой запрос"})
        try:
            d = json.loads(self.rfile.read(n))
            jpg = base64.b64decode(d["photo_b64"]) if d.get("photo_b64") else None
            res = wall_post(d["text"], d["at"], jpg)
            log("пост", res)
            self.reply(200, res)
        except GateError as e:
            log("ошибка:", e.args[0]); self.reply(502, {"ok": False, "error": e.args[0]})
        except (KeyError, ValueError) as e:
            self.reply(400, {"ok": False, "error": f"плохой запрос: {e}"})

    def log_message(self, *a):
        pass


def serve():
    if not (APP_ID and GROUP_ID and KEY): sys.exit("нужны VK_APP_ID, VK_GROUP_ID, NM_GATE_KEY")
    threading.Thread(target=keepalive, daemon=True).start()
    log(f"vkgate слушает 127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "login-url": print(login_url())
    elif cmd == "login" and len(sys.argv) > 2: login(sys.argv[2])
    elif cmd == "check":
        try: print(json.dumps(check(), ensure_ascii=False))
        except GateError as e: print(json.dumps({"ok": False, "error": e.args[0]}, ensure_ascii=False))
    elif cmd == "serve": serve()
    else: sys.exit(__doc__)
