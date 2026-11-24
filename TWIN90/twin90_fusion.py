"""SUPERAMBO FUSION V1 / EVOLUTIVO x TWIN90 HYBRID — SHADOW ONLY.
Only predetermined pre-draw pairs; never wagers, stake sizes or brokerage actions.
No previous system scores are changed. Single pair per mode, scored H1..H5.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from twin90_advance import ROME, MIN_LEAD_SECONDS, next_concorso, ts
from twin90_evolutivo import draw_index

VERSION = "SUPERAMBO_FUSION_V1_SHADOW_FROZEN"
MODES = ("EVOLUTIVO_DECINE_DNA", "EVOLUTIVO_TWIN90_HYBRID")
HORIZONS = (1, 2, 3, 4, 5)
MAX_ACTIVE = 32


def fresh():
    return {
        "version": VERSION, "last_screened": None, "screened": 0,
        "skipped": 0, "published": 0, "missed": 0,
        "active": {}, "recent": [],
        "stats": {
            mode: {
                "published": 0, "completed": 0,
                "by_h": {str(h): {"n": 0, "wins": 0, "control_wins": 0}
                         for h in HORIZONS},
                "within5": {"n": 0, "wins": 0, "control_wins": 0},
            } for mode in MODES
        },
    }


def root(state):
    lab = state.setdefault("superambo_fusion", fresh())
    if lab.get("version") != VERSION:
        raise ValueError("Fusion state version mismatch: refusing to reset")
    return lab


def _numbers(values):
    if (not isinstance(values, list) or len(values) != 20 or
            len(set(values)) != 20 or
            any(type(n) is not int or n < 1 or n > 90 for n in values)):
        raise ValueError("Fusion requires 20 distinct valid pre-draw numbers")
    return values


def _pair(shared, dna):
    # Frozen, deterministic ranking. DNA confirms only a coincident number.
    ranked = sorted(set(shared), key=lambda n: (n not in dna, n))
    return sorted(ranked[:2]) if len(ranked) >= 2 else None


def prepare(state, now=None):
    """Queue no more than one new pair per mode from confirmed source previews."""
    now = now or datetime.now(ROME)
    lab = root(state)
    history = state.get("history") or []
    if not history or not state.get("latest"):
        return describe(state)
    previous = history[-1]
    source = f"{previous['day']}#{int(previous['draw']):03d}"
    if source != state["latest"]:
        return describe(state)
    key, due = next_concorso(previous)
    if lab["last_screened"] == key or now >= due - timedelta(seconds=MIN_LEAD_SECONDS):
        return describe(state)

    pending = next((p for p in state.get("pending_notifications", [])
                    if p.get("type") == "PREVIEW" and p.get("key") == key), None)
    advance = state.get("advance_forecasts", {}).get(key)
    specialist = state.get("specialist_lab", {}).get("forecasts", {}).get(key)
    evo = state.get("ritardatari_evolutivo", {}).get("active", {}).get(key)
    if (not pending or not advance or not specialist or not evo or
            advance.get("status") != "QUEUED" or
            specialist.get("status") != "QUEUED" or
            evo.get("status") != "QUEUED" or
            advance.get("source_key") != source or
            specialist.get("source_key") != source or
            evo.get("source_key") != source):
        return describe(state)

    r = _numbers(specialist["base"]["RITARDATARI"])
    d = _numbers(specialist["base"]["DECINE"])
    control = _numbers(specialist["base"]["CONTROLLO"])
    hybrid = _numbers(advance["simulations"]["HYBRID"]["base"])
    if r != evo["base"]:
        raise ValueError("Frozen EVOLUTIVO source differs from specialist")
    dna = {int(n) for n in (pending.get("dna_master") or {})}
    control_pair = sorted(control)[:2]

    modes = {}
    for mode, other in ((MODES[0], d), (MODES[1], hybrid)):
        shared = sorted(set(r).intersection(other))
        pair = _pair(shared, dna)
        if pair is not None:
            modes[mode] = {
                "pair": pair, "control": control_pair[:],
                "shared": len(shared), "dna_confirmed": any(n in dna for n in pair),
                "hits_by_h": [], "control_by_h": [],
            }
    lab["last_screened"] = key
    lab["screened"] += 1
    if not modes:
        lab["skipped"] += 1
        return describe(state)
    if len(lab["active"]) >= MAX_ACTIVE:
        raise RuntimeError("Fusion active queue capacity reached")

    lab["active"][key] = {
        "version": VERSION, "key": key, "source_key": source,
        "created_at": now.isoformat(), "due_at": due.isoformat(),
        "sent_at": None, "status": "QUEUED",
        "last_h": 0, "modes": modes,
    }
    pending["superambo_fusion"] = {
        "version": VERSION,
        "modes": {name: {"pair": item["pair"], "control": item["control"],
                          "shared": item["shared"], "dna_confirmed": item["dna_confirmed"]}
                  for name, item in modes.items()},
    }
    return describe(state)


def valid_delivery(record):
    try:
        if not record.get("sent_at"):
            return False
        created, sent, due = [ts(record[k])
                              for k in ("created_at", "sent_at", "due_at")]
        return (created <= sent < due - timedelta(seconds=MIN_LEAD_SECONDS) and
                draw_index(record["source_key"]) + 1 == draw_index(record["key"]))
    except (ValueError, TypeError, KeyError):
        return False


def confirm(state, key, when=None):
    """ONLY after Telegram API confirms delivery."""
    lab = root(state)
    record = lab["active"].get(key)
    if not record or record["status"] != "QUEUED":
        return False
    record["sent_at"] = (when or datetime.now(ROME)).isoformat()
    if not valid_delivery(record):
        record["status"] = "LATE"
        return False
    record["status"] = "SENT_BEFORE_DRAW"
    lab["published"] += 1
    for name in record["modes"]:
        lab["stats"][name]["published"] += 1
    return True


def reconcile(state, actual):
    """Score pairs only on consecutive actual draws after valid prepublication."""
    lab = root(state)
    target = f"{actual['day']}#{int(actual['draw']):03d}"
    present = set(actual["base"])
    if len(present) != 20 or any(type(n) is not int or not 1 <= n <= 90 for n in present):
        raise ValueError("Invalid real BASE results")
    index = draw_index(target)
    notes = []
    for key, record in list(lab["active"].items()):
        h = index - draw_index(key) + 1
        if h < 1 or h <= record["last_h"]:
            continue
        if (not valid_delivery(record) or h > 5 or
                h != record["last_h"] + 1):
            lab["missed"] += 1
            lab["active"].pop(key, None)
            continue
        record["last_h"] = h
        for mode, info in record["modes"].items():
            win = int(all(n in present for n in info["pair"]))
            ctrl = int(all(n in present for n in info["control"]))
            info["hits_by_h"].append(win)
            info["control_by_h"].append(ctrl)
            bucket = lab["stats"][mode]["by_h"][str(h)]
            bucket["n"] += 1
            bucket["wins"] += win
            bucket["control_wins"] += ctrl
            if h in (1, 5):
                notes.append({"key": key, "h": h, "mode": mode,
                              "pair": info["pair"], "win": win,
                              "control_win": ctrl})
            if h == 5:
                summary = lab["stats"][mode]["within5"]
                summary["n"] += 1
                summary["wins"] += int(any(info["hits_by_h"]))
                summary["control_wins"] += int(any(info["control_by_h"]))
                lab["stats"][mode]["completed"] += 1
        if h == 5:
            lab["recent"].append({
                "key": key,
                "modes": {m: {"pair": v["pair"], "control": v["control"],
                               "hits_by_h": v["hits_by_h"],
                               "control_by_h": v["control_by_h"]}
                          for m, v in record["modes"].items()}
            })
            lab["recent"] = lab["recent"][-100:]
            lab["active"].pop(key, None)
    return notes


def describe(state):
    lab = root(state)
    return {
        "version": VERSION, "execution": "SHADOW_ONLY_NO_WAGERS",
        "screened": lab["screened"], "skipped": lab["skipped"],
        "published": lab["published"], "missed": lab["missed"],
        "active": len(lab["active"]), "stats": lab["stats"],
    }


def format_extra(message):
    preview = message.get("superambo_fusion")
    notes = message.get("superambo_fusion_results") or []
    lines = []
    if preview:
        lines += ["", "🧩 SUPERAMBO FUSION V1 — SOLO SHADOW"]
        for mode, info in preview["modes"].items():
            short = "DECINE + DNA" if mode == MODES[0] else "EVOLUTIVO + HYBRID"
            pair = "-".join(f"{n:02d}" for n in info["pair"])
            lines.append(f"{short}: {pair} | {info['shared']} numeri comuni")
        lines.append("Coppie virtuali H1–H5; nessuna puntata.")
    if notes:
        lines += ["", "🧩 FUSION — RISULTATI AMBI PREVENTIVI"]
        for item in notes:
            short = "DECINE" if item["mode"] == MODES[0] else "HYBRID"
            lines.append(f"{short} {item['key']} H{item['h']}: "
                         f"{'AMBO' if item['win'] else 'NO'} "
                         f"(controllo {'AMBO' if item['control_win'] else 'NO'})")
    return "\n".join(lines)
