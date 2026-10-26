"""Озвучка «Видео дня» через ElevenLabs: весь текст сценария одним файлом.

python3 -m nm.voice make --scenario scenario.json [--out voiceover.wav]   # пишет файл и поле "voiceover" в сценарий
python3 -m nm.voice voices                                               # голоса аккаунта: id, имя, категория

Ключ — ELEVENLABS_API_KEY, голос — ELEVENLABS_VOICE_ID или config.json → video_of_day.eleven_voice_id.
Текст для диктора собирается из "say" всех сцен + концовка (как в clipkit): из {цифры|слова} берутся слова, «+» убирается.
Паузы сжимаются (ffmpeg), при «э»/«эм» (Whisper) — до 3 попыток с другим seed.
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


FILLER = re.compile(r"^(э+|эм+|ээ+м*|м+|а+|хм+)$")


def tts(text, seed):
    o = cfg().get("video_of_day", {})
    body = json.dumps({"text": text, "model_id": o.get("eleven_model", "eleven_multilingual_v2"), "seed": seed,
                       "apply_text_normalization": "on",
                       "voice_settings": {"stability": 0.75, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}}).encode()
    audio = http(f"{API}/text-to-speech/{voice_id()}?output_format=mp3_44100_128", data=body, timeout=180, raw=True,
                 headers={"xi-api-key": need("ELEVENLABS_API_KEY"), "Content-Type": "application/json", "Accept": "audio/mpeg"})
    if len(audio) < 5000 or audio[:1] == b"{":
        die(f"ElevenLabs не вернул звук: {audio[:300].decode('utf-8', 'replace')}")
    return audio


def tighten(src, dst):
    """Паузы длиннее 0,3 с сжимаем до 0,25 с, тишину в начале убираем."""
    import subprocess
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:"
          "stop_periods=-1:stop_duration=0.3:stop_threshold=-45dB:stop_silence=0.25")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", af, "-ac", "1", "-ar", "48000", dst], check=True)


def fillers(path):
    """Слова-паразиты («э», «эм»…) по распознаванию Whisper; None — если Whisper не установлен."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    md = os.path.expanduser("~/video/models")
    segs, _ = WhisperModel("base", device="cpu", compute_type="int8", download_root=md).transcribe(
        path, language="ru", word_timestamps=True, initial_prompt="Э-э, эм, ну, это самое.")
    return [w.word.strip() for sg in segs for w in sg.words if FILLER.match(re.sub(r"[^\wё]", "", w.word.lower()))]


def make(scn, dst):
    S = json.load(open(scn, encoding="utf-8"))
    text = script(S)
    base = os.path.dirname(os.path.abspath(scn))
    dst = dst if os.path.isabs(dst) else os.path.join(base, dst)
    best = None
    for k, seed in enumerate((11, 23, 37)):  # до 3 попыток, если в озвучке «э»/«эм»
        raw = os.path.join(base, f"vo_raw{k}.mp3")
        with open(raw, "wb") as f:
            f.write(tts(text, seed))
        clean = os.path.join(base, f"vo_clean{k}.wav")
        tighten(raw, clean)
        bad = fillers(clean)
        if best is None or (bad is not None and len(bad) < len(best[1] or [])):
            best = (clean, bad)
        if not bad:
            break
    os.replace(best[0], dst)
    S["voiceover"] = dst
    json.dump(S, open(scn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out({"ok": True, "file": dst, "chars": len(text), "tries": k + 1, "fillers": best[1], "text": text})


def voices():
    r = http(f"{API}/voices", headers={"xi-api-key": need("ELEVENLABS_API_KEY")})
    if "voices" not in r:
        die(f"ElevenLabs: {r}")
    out({"ok": True, "voices": [{"id": v["voice_id"], "name": v["name"], "category": v.get("category")} for v in r["voices"]]})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "voices"])
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="voiceover.wav")
    a = ap.parse_args()
    make(a.scenario, a.out) if a.cmd == "make" else voices()
