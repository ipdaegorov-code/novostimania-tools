"""Какой сейчас слот. python3 -m nm.slot [--at HH:MM]
Выдаёт рубрику, время слота (unix), срок диалога с владельцем (unix) и дату для картинки."""
import argparse
from nm.common import cfg, now, slot_for, out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--at", help="принудительно слот HH:MM (если указан в запуске)")
    g = ap.parse_args(); c = cfg(); n = now()
    if g.at:
        s = next((x for x in c["slots"] if x["time"] == g.at), None)
        if not s: out({"ok": False, "error": f"нет слота {g.at}"}); return
        hh, mm = map(int, g.at.split(":")); t = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
    else:
        s, t = slot_for(n)
    if not s:
        out({"ok": True, "slot": None, "note": "подходящего слота сегодня нет — ничего не делай"}); return
    lead = c["approve_lead_minutes"] * 60
    out({"ok": True, "slot": s, "slot_unix": int(t.timestamp()), "approve_until": int(t.timestamp()) - lead,
         "now": n.strftime("%H:%M"), "date": n.strftime("%d.%m.%Y"), "weekday": n.strftime("%A"),
         "length": c["post_length"]["news" if s["kind"] == "news" else "digest"], "photo_order": c["photo_order"][s["photos"]]})


if __name__ == "__main__":
    main()
