"""AMBATA GUIDA V1: fixed, prospective, one-anchor one-pair SHADOW lab.

Do not wager. At a frozen 60-draw lookback, choose the most persistent
ambata across two 30-draw halves. Rank its partner using only previously
observed co-occurrences/frequency and prepublished specialist forecasts.
One forecast per 12 draws (one hour) when source and timing are valid.
Compare with a two-number frequency baseline. Measure H1-H5 and
1 EUR virtual stake, gross 14 EUR/pair hit, FULL5 vs first-win STOP1.
The anchor is not guaranteed to be predictable; all results are exploratory.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from collections import Counter

from twin90_advance import ROME, MIN_LEAD_SECONDS, next_concorso, ts
from twin90_evolutivo import draw_index
from twin90_fusion import valid_delivery

VERSION = "AMBATA_GUIDA_V1_SHADOW_FROZEN"
LOOKBACK = 60
HALF = 30
SLOT_EVERY_DRAWS = 12
MIN_HALF_APPEARANCES = 8
MAX_ACTIVE = 16
HORIZON = 5
STAKE = 1
GROSS = 14


def money():
    return {"spent_eur": 0, "gross_eur": 0, "net_eur": 0,
            "control_spent_eur": 0, "control_gross_eur": 0,
            "control_net_eur": 0}


def fresh():
    return {
        "version": VERSION, "screened": 0, "skipped": 0, "published": 0,
        "completed": 0, "missed": 0, "last_screened": None,
        "active": {}, "recent": [], "daily": {}, "weekly": {},
        "stats": {"n": 0, "anchor_h1": 0, "anchor_h5": 0,
                  "pair_h1": 0, "pair_h5": 0, "control_h1": 0,
                  "control_h5": 0,
                  "FULL5": money(), "STOP1": money()},
    }


def root(state):
    lab = state.setdefault("ambata_guida", fresh())
    if lab.get("version") != VERSION:
        raise ValueError("AMBATA GUIDA version mismatch; refusing reset")
    return lab


def choose(history, specialist, hybrid):
    """Return fully frozen candidates; requires 60 actual BASE draws."""
    if len(history) < LOOKBACK:
        return None
    window = history[-LOOKBACK:]
    if any(len(row.get("base", [])) != 20 or
           len(set(row["base"])) != 20 or
           any(type(n) is not int or not 1 <= n <= 90 for n in row["base"])
           for row in window):
        raise ValueError("Invalid BASE in lookback")
    left = Counter(n for row in window[:HALF] for n in row["base"])
    right = Counter(n for row in window[HALF:] for n in row["base"])
    total = left + right
    guide = sorted(range(1, 91),
                   key=lambda n: (-min(left[n], right[n]), -total[n], n))[0]
    if min(left[guide], right[guide]) < MIN_HALF_APPEARANCES:
        return None
    # Every bonus is computed from pre-draw specialist inputs.
    decine = set(specialist["DECINE"])
    evolutivo = set(specialist["RITARDATARI"])
    hybrid = set(hybrid)
    counts_together = Counter(
        n for row in window if guide in row["base"]
        for n in row["base"] if n != guide
    )
    candidates = [n for n in range(1, 91) if n != guide]
    def score(n):
        return (3 * counts_together[n] + total[n]
                + 4 * int(n in decine) + 3 * int(n in hybrid)
                + 2 * int(n in evolutivo))
    partner = sorted(candidates, key=lambda n: (-score(n), n))[0]
    baseline = sorted(range(1, 91), key=lambda n: (-total[n], n))[:2]
    return {
        "anchor": guide, "partner": partner,
        "pair": sorted([guide, partner]), "control": sorted(baseline),
        "half_appearances": [left[guide], right[guide]],
        "frequency_60": total[guide],
        "partner_score": score(partner),
    }


def prepare(state, now=None):
    now = now or datetime.now(ROME)
    lab = root(state)
    if not state.get("history") or not state.get("latest"):
        return describe(state)
    last = state["history"][-1]
    source = f"{last['day']}#{int(last['draw']):03d}"
    if source != state["latest"]:
        return describe(state)
    key, due = next_concorso(last)
    if draw_index(key) % SLOT_EVERY_DRAWS != 0:
        return describe(state)
    if lab["last_screened"] == key or now >= due - timedelta(seconds=MIN_LEAD_SECONDS):
        return describe(state)
    pending = next((p for p in state.get("pending_notifications", [])
                    if p.get("type") == "PREVIEW" and p.get("key") == key), None)
    advance = state.get("advance_forecasts", {}).get(key)
    specialist = state.get("specialist_lab", {}).get("forecasts", {}).get(key)
    if not pending or not advance or not specialist:
        return describe(state)
    if any(rec.get("source_key") != source or rec.get("status") != "QUEUED"
           for rec in (advance, specialist)):
        return describe(state)
    if len(lab["active"]) >= MAX_ACTIVE:
        raise RuntimeError("AMBATA GUIDA queue capacity reached")
    specialist_base = specialist.get("base", {})
    for field in ("DECINE", "RITARDATARI"):
        values = specialist_base.get(field)
        if (not isinstance(values, list) or len(values) != 20 or
                len(set(values)) != 20):
            raise ValueError("Invalid specialist preview")
    hybrid = advance.get("simulations", {}).get("HYBRID", {}).get("base")
    if not isinstance(hybrid, list) or len(hybrid) != 20 or len(set(hybrid)) != 20:
        raise ValueError("Invalid HYBRID preview")
    selection = choose(state["history"], specialist_base, hybrid)
    lab["last_screened"] = key
    lab["screened"] += 1
    if selection is None:
        lab["skipped"] += 1
        return describe(state)
    lab["active"][key] = {
        "key": key, "source_key": source,
        "created_at": now.isoformat(), "due_at": due.isoformat(),
        "sent_at": None, "status": "QUEUED", "last_h": 0,
        **selection,
        "anchor_hits": [], "pair_hits": [], "control_hits": [],
        "policies": {
            p: {"live": True, "control_live": True, **money()}
            for p in ("FULL5", "STOP1")
        },
    }
    pending["ambata_guida"] = {
        "version": VERSION, "pair": selection["pair"],
        "anchor": selection["anchor"], "control": selection["control"],
        "half_appearances": selection["half_appearances"],
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
    return True


def add_money(row, spent, gross, ctrl_spent, ctrl_gross):
    row["spent_eur"] += spent
    row["gross_eur"] += gross
    row["net_eur"] += gross - spent
    row["control_spent_eur"] += ctrl_spent
    row["control_gross_eur"] += ctrl_gross
    row["control_net_eur"] += ctrl_gross - ctrl_spent


def reconcile(state, actual):
    lab = root(state)
    key = f"{actual['day']}#{int(actual['draw']):03d}"
    values = actual["base"]
    if (len(values) != 20 or len(set(values)) != 20 or
            any(type(n) is not int or not 1 <= n <= 90 for n in values)):
        raise ValueError("Invalid verified BASE draw")
    present = set(values)
    index = draw_index(key)
    notes = []
    for forecast_key, rec in list(lab["active"].items()):
        h = index - draw_index(forecast_key) + 1
        if h < 1 or h <= rec["last_h"]:
            continue
        if (not valid_delivery(rec) or h > HORIZON or
                h != rec["last_h"] + 1):
            lab["missed"] += 1
            lab["active"].pop(forecast_key, None)
            continue
        rec["last_h"] = h
        anchor_hit = int(rec["anchor"] in present)
        pair_hit = int(all(n in present for n in rec["pair"]))
        ctrl_hit = int(all(n in present for n in rec["control"]))
        rec["anchor_hits"].append(anchor_hit)
        rec["pair_hits"].append(pair_hit)
        rec["control_hits"].append(ctrl_hit)
        weekly = datetime.fromisoformat(actual["day"]).isocalendar()
        week = f"{weekly.year}-W{weekly.week:02d}"
        for policy, account in rec["policies"].items():
            place = policy == "FULL5" or account["live"]
            ctrl_place = policy == "FULL5" or account["control_live"]
            spent = STAKE if place else 0
            gross = GROSS * STAKE * pair_hit if place else 0
            ctrl_spent = STAKE if ctrl_place else 0
            ctrl_gross = GROSS * STAKE * ctrl_hit if ctrl_place else 0
            for bucket in (
                account,
                lab["stats"][policy],
                lab["daily"].setdefault(actual["day"], {}).setdefault(policy, money()),
                lab["weekly"].setdefault(week, {}).setdefault(policy, money()),
            ):
                add_money(bucket, spent, gross, ctrl_spent, ctrl_gross)
            if pair_hit:
                account["live"] = False
            if ctrl_hit:
                account["control_live"] = False
        if h == HORIZON:
            stats = lab["stats"]
            stats["n"] += 1
            stats["anchor_h1"] += rec["anchor_hits"][0]
            stats["anchor_h5"] += int(any(rec["anchor_hits"]))
            stats["pair_h1"] += rec["pair_hits"][0]
            stats["pair_h5"] += int(any(rec["pair_hits"]))
            stats["control_h1"] += rec["control_hits"][0]
            stats["control_h5"] += int(any(rec["control_hits"]))
            lab["completed"] += 1
            note = {
                "key": forecast_key, "anchor": rec["anchor"],
                "pair": rec["pair"], "control": rec["control"],
                "anchor_h5": bool(any(rec["anchor_hits"])),
                "pair_h5": bool(any(rec["pair_hits"])),
                "control_h5": bool(any(rec["control_hits"])),
                "full5_net": rec["policies"]["FULL5"]["net_eur"],
                "stop1_net": rec["policies"]["STOP1"]["net_eur"],
                "full5_control_net": rec["policies"]["FULL5"]["control_net_eur"],
                "stop1_control_net": rec["policies"]["STOP1"]["control_net_eur"],
            }
            lab["recent"].append(note)
            lab["recent"] = lab["recent"][-100:]
            notes.append(note)
            lab["active"].pop(forecast_key, None)
    return notes


def describe(state):
    lab = root(state)
    return {
        "version": VERSION, "execution": "SHADOW_ONLY_NO_WAGERS",
        "published": lab["published"], "screened": lab["screened"],
        "skipped": lab["skipped"], "missed": lab["missed"],
        "completed": lab["completed"], "active": len(lab["active"]),
        "stats": lab["stats"], "daily": lab["daily"], "weekly": lab["weekly"],
    }


def format_extra(message):
    preview = message.get("ambata_guida")
    notes = message.get("ambata_guida_results") or []
    lines = []
    if preview:
        lines.append("\n🎯 AMBATA GUIDA V1 — SOLO SHADOW")
        lines.append(f"Ambata: {preview['anchor']:02d} | "
                     f"conferme 30+30: {preview['half_appearances']}")
        pair = "-".join(f"{n:02d}" for n in preview["pair"])
        lines.append(f"AMBO PRINCIPALE: {pair} | H1–H5")
        lines.append("Confronto virtuale e saldo 1€ per colpo, nessuna puntata.")
    if notes:
        lines.append("\n🎯 AMBATA GUIDA — RISULTATI H5")
        for note in notes:
            lines.append(f"{note['key']}: ambata "
                         f"{'SI' if note['anchor_h5'] else 'NO'}, ambo "
                         f"{'SI' if note['pair_h5'] else 'NO'}, "
                         f"FULL5 {note['full5_net']:+d}€, "
                         f"STOP1 {note['stop1_net']:+d}€")
    return "\n".join(lines)
