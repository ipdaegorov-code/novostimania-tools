"""Озвучка «Видео дня» через ElevenLabs: весь текст сценария одним файлом.

python3 -m nm.voice make --scenario scenario.json [--out voiceover.mp3]   # пишет файл и поле "voiceover" в сценарий
python3 -m nm.voice voices                                               # голоса аккаунта: id, имя, категория

Ключ — ELEVENLABS_API_KEY, голос — ELEVENLABS_VOICE_ID или config.json → video_of_day.eleven_voice_id.
Текст для диктора собирается из "say" всех сцен + концовка (как в clipkit): из {цифры|слова} берутся слова, «+» убирается.
Нет ключа/голоса или ошибка API — {"ok": false, …}; тогда clipkit озвучит офлайн-голосом (поле "voiceover" не ставим).
"""
import argparse, json, os, re
from nm.common import cfg, http, out, die, need

API = "https://api.elevenlabs.io/v1"
OUTRO_SAY = "Подписывайся на Новостим+анию — завтра будет новое видео."
TOK = re.compile(r"\{([^|}]+)\|([^}]+)\}|(\S+)")


def spoken(say):
    t = " ".join(m.group(2) if m.group(1) else m.group(3) for m in TOK.finditer(say)).replace("+", "")
    return re.sub(r"\s+([.,!?:;…»)])", r"\1", t).strip()


def script(S):
    parts = [spoken(s["say"]) for s in S["scenes"] if s.get("type") != "outro" and s.get("say")]
    parts.append(spoken(S.get("outro_say", OUTRO_SAY)))
    return " ".join(p if re.search(r"[.!?…]$", p) else p + "." for p in parts)


def voice_id():
    v = os.environ.get("ELEVENLABS_VOICE_ID") or cfg().get("video_of_day", {}).get("eleven_voice_id")
    if not v:
        die("не задан голос ElevenLabs (ELEVENLABS_VOICE_ID или video_of_day.eleven_voice_id)")
    return v


def make(scn, dst):
    S = json.load(open(scn, encoding="utf-8"))
    text = script(S)
    o = cfg().get("video_of_day", {})
    body = json.dumps({"text": text, "model_id": o.get("eleven_model", "eleven_multilingual_v2"),
                       "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}}).encode()
    audio = http(f"{API}/text-to-speech/{voice_id()}?output_format=mp3_44100_128", data=body, timeout=180, raw=True,
                 headers={"xi-api-key": need("ELEVENLABS_API_KEY"), "Content-Type": "application/json", "Accept": "audio/mpeg"})
    if len(audio) < 5000 or audio[:1] == b"{":
        die(f"ElevenLabs не вернул звук: {audio[:300].decode('utf-8', 'replace')}")
    base = os.path.dirname(os.path.abspath(scn))
    dst = dst if os.path.isabs(dst) else os.path.join(base, dst)
    with open(dst, "wb") as f:
        f.write(audio)
    S["voiceover"] = dst
    json.dump(S, open(scn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out({"ok": True, "file": dst, "chars": len(text), "text": text})


def voices():
    r = http(f"{API}/voices", headers={"xi-api-key": need("ELEVENLABS_API_KEY")})
    if "voices" not in r:
        die(f"ElevenLabs: {r}")
    out({"ok": True, "voices": [{"id": v["voice_id"], "name": v["name"], "category": v.get("category")} for v in r["voices"]]})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "voices"])
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="voiceover.mp3")
    a = ap.parse_args()
    make(a.scenario, a.out) if a.cmd == "make" else voices()
