"""RITARDATARI EVOLUTIVO V1 — frozen selective SHADOW, no wagers.

This is a preannounced filter over the UNCHANGED SPECIALIST LAB RITARDATARI
20-number preview. Uses only the prior 288 observed, verified BASE draws.
Every published signal compares with the existing 20-number CONTROLLO on
the identical target draw. H1/H2/H5 count unique appearances (not bets).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from twin90_advance import MIN_LEAD_SECONDS, ROME, next_concorso, ts

VERSION = "RITARDATARI_EVOLUTIVO_V1_FROZEN"
WARMUP = 288
MAX_ACTIVE = 16
HORIZONS = (1, 2, 5)


def draw_index(key):
    day, number = key.split("#", 1)
    num = int(number)
    if not 1 <= num <= 288:
        raise ValueError("Invalid draw number")
    return date.fromisoformat(day).toordinal() * 288 + num


def rowkey(row):
    return f"{row['day']}#{int(row['draw']):03d}"


def _empty():
    return {
        "version": VERSION,
        "screened": 0, "passed": 0, "rejected": 0,
        "published": 0, "missed": 0,
        "last_screened": None, "last_filter": None,
        "active": {}, "recent": [],
        "stats": {
            str(h): {"n": 0, "hits": 0, "ge7": 0, "ge8": 0,
                     "control_hits": 0, "control_ge7": 0, "control_ge8": 0}
            for h in HORIZONS
        }
    }


def root(state):
    lab = state.setdefault("ritardatari_evolutivo", _empty())
    if lab.get("version") != VERSION:
        raise ValueError("RITARDATARI EVOLUTIVO version mismatch")
    return lab


def ages(history):
    """Elapsed OBSERVED real draws since each last BASE occurrence."""
    if len(history) < WARMUP:
        raise ValueError("288 real BASE draws required")
    history = history[-WARMUP:]
    seen_keys = set()
    for row in history:
        key = rowkey(row)
        if key in seen_keys:
            raise ValueError("Duplicate real draw in warmup")
        seen_keys.add(key)
        nums = row["base"]
        if len(nums) != 20 or len(set(nums)) != 20 or any(
            type(n) is not int or not 1 <= n <= 90 for n in nums
        ):
            raise ValueError("Invalid real BASE history")
    values = [WARMUP] * 91
    for back, row in enumerate(reversed(history)):
        for number in row["base"]:
            if values[number] == WARMUP:
                values[number] = back
    return values


def filters(history, selected):
    """Frozen rules A (mean>=6), B (short<=9), C (long>=5)."""
    if len(selected) != 20 or len(set(selected)) != 20 or any(
        type(n) is not int or not 1 <= n <= 90 for n in selected
    ):
        raise ValueError("Invalid specialist prediction")
    prior = history[-WARMUP:]
    a = ages(prior)
    chosen_ages = [a[n] for n in selected]
    mean = sum(chosen_ages) / 20
    short = sum(g <= 4 for g in chosen_ages)
    long = sum(g >= 10 for g in chosen_ages)
    gaps = sum(
        draw_index(rowkey(right)) != draw_index(rowkey(left)) + 1
        for left, right in zip(prior, prior[1:])
    )
    return {
        "mean_gap": round(mean, 2), "short_0_4": short, "long_10_plus": long,
        "missing_transitions": gaps,
        "A": mean >= 6.0,
        "B": short <= 9,
        "C": long >= 5,
        "pass": mean >= 6.0 and short <= 9 and long >= 5,
    }


def prepare(state, now=None):
    """Use only a queued advance preview with existing specialist numbers."""
    now = now or datetime.now(ROME)
    lab = root(state)
    history = state.get("history") or []
    if len(history) < WARMUP or not state.get("latest"):
        return None
    if rowkey(history[-1]) != state["latest"]:
        return None
    key, due = next_concorso(history[-1])
    if lab["last_screened"] == key or now >= due - timedelta(seconds=MIN_LEAD_SECONDS):
        return None
    pending = next((p for p in state.get("pending_notifications", [])
                    if p.get("type") == "PREVIEW" and p.get("key") == key), None)
    spec = (state.get("specialist_lab") or {}).get("forecasts", {}).get(key)
    if pending is None or spec is None or spec.get("status") != "QUEUED":
        return None
    if spec.get("source_key") != state["latest"] or spec.get("sent_at"):
        return None
    original = spec["base"]["RITARDATARI"]
    control = spec["base"]["CONTROLLO"]
    if (len(control) != 20 or len(set(control)) != 20 or
        any(type(n) is not int or not 1 <= n <= 90 for n in control)):
        raise ValueError("Invalid specialist control")
    measured = filters(history, original)
    lab["screened"] += 1
    lab["last_screened"] = key
    lab["last_filter"] = {"key": key, **measured}
    if not measured["pass"]:
        lab["rejected"] += 1
        return None
    lab["passed"] += 1
    record = {
        "version": VERSION, "key": key, "source_key": state["latest"],
        "due_at": due.isoformat(), "created_at": now.isoformat(),
        "sent_at": None, "status": "QUEUED",
        "base": list(original), "control": list(control),
        "filter": measured, "seen": [], "last_h": 0,
    }
    if len(lab["active"]) >= MAX_ACTIVE:
        raise RuntimeError("Too many unscored active EVOLUTIVO forecasts")
    lab["active"][key] = record
    pending["ritardatari_evolutivo"] = {
        "version": VERSION, "base": list(original), "filter": measured
    }
    return key


def valid_delivery(record):
    try:
        if not record.get("sent_at"):
            return False
        made, sent, due = (ts(record[k]) for k in ("created_at", "sent_at", "due_at"))
        return (
            made <= sent < due - timedelta(seconds=MIN_LEAD_SECONDS) and
            draw_index(record["source_key"]) + 1 == draw_index(record["key"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def confirm(state, key, when=None):
    """Call only after a successful Telegram API delivery acknowledgement."""
    record = root(state)["active"].get(key)
    if not record or record["status"] != "QUEUED":
        return False
    record["sent_at"] = (when or datetime.now(ROME)).isoformat()
    if valid_delivery(record):
        record["status"] = "SENT_BEFORE_DRAW"
        root(state)["published"] += 1
        return True
    record["status"] = "LATE"
    return False


def reconcile(state, actual):
    """Score only delivered prospective signals, once at H1/H2/H5.

    If a source draw is missing in the outcome interval, close as incomplete
    rather than pretending that H2/H5 were consecutive.
    """
    lab = root(state)
    current = draw_index(rowkey(actual))
    if len(actual["base"]) != 20 or len(set(actual["base"])) != 20:
        raise ValueError("Invalid real outcome")
    present = set(actual["base"])
    notes = []
    for key, record in list(lab["active"].items()):
        h = current - draw_index(key) + 1
        if h < 1:
            continue
        if h <= record["last_h"]:
            continue  # Duplicate real draw: never score or invalidate twice.
        if not valid_delivery(record) or h > max(HORIZONS) or h != record["last_h"] + 1:
            lab["missed"] += 1
            record["status"] = "INCOMPLETE"
            lab["active"].pop(key, None)
            continue
        record["last_h"] = h
        record["seen"] = sorted(set(record["seen"]) | present)
        if h in HORIZONS:
            seen = set(record["seen"])
            hits = sorted(seen.intersection(record["base"]))
            control_hits = sorted(seen.intersection(record["control"]))
            s = lab["stats"][str(h)]
            s["n"] += 1
            s["hits"] += len(hits)
            s["ge7"] += int(len(hits) >= 7)
            s["ge8"] += int(len(hits) >= 8)
            s["control_hits"] += len(control_hits)
            s["control_ge7"] += int(len(control_hits) >= 7)
            s["control_ge8"] += int(len(control_hits) >= 8)
            notes.append({
                "key": key, "h": h, "hits": len(hits),
                "control_hits": len(control_hits), "numbers": hits,
                "n": s["n"], "ge7": s["ge7"], "ge8": s["ge8"],
            })
            if h == 5:
                lab["recent"].append(notes[-1])
                lab["recent"] = lab["recent"][-100:]
                record["status"] = "COMPLETE"
                lab["active"].pop(key, None)
    return notes


def describe(state):
    lab = root(state)
    return {
        "version": VERSION, "warmup": len(state.get("history", [])[-WARMUP:]),
        "required": WARMUP,
        "screened": lab["screened"], "passed": lab["passed"],
        "rejected": lab["rejected"], "published": lab["published"],
        "missed": lab["missed"], "active": len(lab["active"]),
        "last_filter": lab["last_filter"], "stats": lab["stats"],
        "mode": "SHADOW_ONLY_NO_WAGERS",
    }


def format_extra(message):
    lines = []
    preview = message.get("ritardatari_evolutivo")
    if preview:
        f = preview["filter"]
        lines.extend([
            "", "🧬 RITARDATARI EVOLUTIVO V1 — SHADOW",
            "BASE: " + " ".join(f"{n:02d}" for n in preview["base"]),
            f"Filtri A/B/C OK | ritardo medio {f['mean_gap']:.2f} | "
            f"R0–4 {f['short_0_4']}/20 | R10+ {f['long_10_plus']}/20",
            "Segnale sperimentale; nessuna giocata.",
        ])
    results = message.get("ritardatari_evolutivo_results") or []
    if results:
        lines.append("")
        lines.append("🧬 EVOLUTIVO — VERIFICA PREVENTIVA")
        for r in results:
            lines.append(
                f"{r['key']} H{r['h']}: {r['hits']}/20 "
                f"(controllo {r['control_hits']}/20) | "
                f"totale {r['ge7']} da 7+ e {r['ge8']} da 8+ su {r['n']}"
            )
    return "\n".join(lines)
