"""SUPERAMBO MULTI-2/3/5: prospective shadow-only pair coverage lab.

No wagers. No changes to the frozen Fusion V1 counters. Each preview must
be acknowledged before the draw; scoring uses consecutive verified BASE draws.
The controls use the same number of deterministic pairs as each experiment.
"""
from __future__ import annotations

from datetime import datetime
from itertools import combinations

from twin90_advance import ROME
from twin90_evolutivo import draw_index
from twin90_fusion import MODES, root as fusion_root, valid_delivery

VERSION = "SUPERAMBO_MULTI_235_SHADOW_V1"
SIZES = (2, 3, 5)
HORIZONS = (1, 2, 3, 4, 5)
MAX_ACTIVE = 32


def fresh():
    return {
        "version": VERSION, "last_prepared": None, "published": 0,
        "missed": 0, "active": {}, "recent": [],
        "stats": {mode: {str(size): {
            "published": 0, "completed": 0, "within5": {"n": 0, "wins": 0, "control_wins": 0},
            "by_h": {str(h): {"n": 0, "wins": 0, "pair_hits": 0,
                              "pair_exposures": 0, "control_wins": 0,
                              "control_pair_hits": 0, "control_pair_exposures": 0}
                     for h in HORIZONS},
        } for size in SIZES} for mode in MODES},
    }


def root(state):
    obj = state.setdefault("superambo_multi", fresh())
    if obj.get("version") != VERSION:
        raise ValueError("Multi lab version mismatch: refusing to reset")
    return obj


def pairs(values):
    vals = sorted(set(values))
    return [list(v) for v in combinations(vals, 2)]


def prepare(state, now=None):
    """Only build from a new, already preselected Fusion V1 QUEUED preview."""
    now = now or datetime.now(ROME)
    lab = root(state)
    frozen = fusion_root(state)
    if not state.get("history"):
        return describe(state)
    last = state["history"][-1]
    source = f"{last['day']}#{int(last['draw']):03d}"
    candidate = next((rec for rec in frozen["active"].values()
                      if rec["source_key"] == source and rec["status"] == "QUEUED"), None)
    if not candidate or lab["last_prepared"] == candidate["key"]:
        return describe(state)
    key = candidate["key"]
    pending = next((p for p in state.get("pending_notifications", [])
                    if p.get("type") == "PREVIEW" and p.get("key") == key), None)
    spec = state.get("specialist_lab", {}).get("forecasts", {}).get(key)
    advance = state.get("advance_forecasts", {}).get(key)
    if not pending or not spec or not advance:
        return describe(state)
    if len(lab["active"]) >= MAX_ACTIVE:
        raise RuntimeError("Multi lab active queue capacity reached")
    r = spec["base"]["RITARDATARI"]
    control = spec["base"]["CONTROLLO"]
    comparisons = {
        MODES[0]: spec["base"]["DECINE"],
        MODES[1]: advance["simulations"]["HYBRID"]["base"],
    }
    modes = {}
    for mode, other in comparisons.items():
        if mode not in candidate["modes"]:
            continue
        options = pairs(set(r) & set(other))
        if not options:
            continue
        # Always prioritize the existing frozen V1 choice, without changing it.
        primary = candidate["modes"][mode]["pair"]
        options.sort(key=lambda p: (p != primary, p))
        controls = pairs(control)
        modes[mode] = {
            str(k): {"pairs": options[:k], "controls": controls[:min(k, len(options))],
                     "hits": [], "control_hits": []}
            for k in SIZES
        }
    lab["last_prepared"] = key
    if not modes:
        return describe(state)
    lab["active"][key] = {
        "key": key, "source_key": source, "created_at": candidate["created_at"],
        "due_at": candidate["due_at"], "sent_at": None, "status": "QUEUED",
        "last_h": 0, "modes": modes,
    }
    pending["superambo_multi"] = {
        "version": VERSION,
        "modes": {mode: {k: v["pairs"] for k, v in variants.items()}
                  for mode, variants in modes.items()},
    }
    return describe(state)


def confirm(state, key, when=None):
    lab = root(state)
    rec = lab["active"].get(key)
    if not rec or rec["status"] != "QUEUED":
        return False
    rec["sent_at"] = (when or datetime.now(ROME)).isoformat()
    if not valid_delivery(rec):
        rec["status"] = "LATE"
        return False
    rec["status"] = "SENT_BEFORE_DRAW"
    lab["published"] += 1
    for mode, variants in rec["modes"].items():
        for size in variants:
            lab["stats"][mode][size]["published"] += 1
    return True


def reconcile(state, actual):
    lab = root(state)
    key = f"{actual['day']}#{int(actual['draw']):03d}"
    index = draw_index(key)
    base = actual["base"]
    if len(base) != 20 or len(set(base)) != 20 or any(
            type(n) is not int or not 1 <= n <= 90 for n in base):
        raise ValueError("Invalid BASE draw")
    values = set(base)
    notes = []
    for forecast_key, rec in list(lab["active"].items()):
        h = index - draw_index(forecast_key) + 1
        if h < 1 or h <= rec["last_h"]:
            continue
        if not valid_delivery(rec) or h > 5 or h != rec["last_h"] + 1:
            lab["missed"] += 1
            lab["active"].pop(forecast_key, None)
            continue
        rec["last_h"] = h
        for mode, variants in rec["modes"].items():
            for size, item in variants.items():
                actual_hits = sum(int(set(p).issubset(values)) for p in item["pairs"])
                control_hits = sum(int(set(p).issubset(values)) for p in item["controls"])
                item["hits"].append(actual_hits)
                item["control_hits"].append(control_hits)
                bucket = lab["stats"][mode][size]["by_h"][str(h)]
                bucket["n"] += 1
                bucket["wins"] += int(actual_hits > 0)
                bucket["pair_hits"] += actual_hits
                bucket["pair_exposures"] += len(item["pairs"])
                bucket["control_wins"] += int(control_hits > 0)
                bucket["control_pair_hits"] += control_hits
                bucket["control_pair_exposures"] += len(item["controls"])
                if h == 5:
                    total = lab["stats"][mode][size]["within5"]
                    total["n"] += 1
                    total["wins"] += int(any(item["hits"]))
                    total["control_wins"] += int(any(item["control_hits"]))
                    lab["stats"][mode][size]["completed"] += 1
                    notes.append({"key": forecast_key, "mode": mode, "size": int(size),
                                  "win": bool(any(item["hits"])),
                                  "control_win": bool(any(item["control_hits"]))})
        if h == 5:
            lab["recent"].append({
                "key": forecast_key,
                "modes": {mode: {size: {"pairs": v["pairs"], "hits": v["hits"],
                                           "control_hits": v["control_hits"]}
                                 for size, v in variants.items()}
                          for mode, variants in rec["modes"].items()},
            })
            lab["recent"] = lab["recent"][-100:]
            lab["active"].pop(forecast_key, None)
    return notes


def describe(state):
    obj = root(state)
    return {
        "version": VERSION, "execution": "SHADOW_ONLY_NO_WAGERS",
        "published": obj["published"], "missed": obj["missed"],
        "active": len(obj["active"]), "stats": obj["stats"],
    }


def format_extra(message):
    preview = message.get("superambo_multi")
    results = message.get("superambo_multi_results") or []
    lines = []
    if preview:
        lines.append("\n🧪 FUSION MULTI-2/3/5 — SOLO SHADOW")
        for mode, variants in preview["modes"].items():
            label = "DECINE" if mode == MODES[0] else "HYBRID"
            for size, chosen in variants.items():
                formatted = ", ".join("-".join(f"{n:02d}" for n in p) for p in chosen)
                lines.append(f"{label} MULTI-{size}: {formatted}")
        lines.append("Verifica H1–H5, nessuna puntata.")
    if results:
        lines.append("\n🧪 FUSION MULTI — ESITI H5")
        for note in results:
            label = "DECINE" if note["mode"] == MODES[0] else "HYBRID"
            lines.append(f"{label} MULTI-{note['size']} {note['key']}: "
                         f"{'AMBO' if note['win'] else 'NO'} "
                         f"(controllo {'AMBO' if note['control_win'] else 'NO'})")
    return "\n".join(lines)
