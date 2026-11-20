"""TWIN90 SPECIALIST LAB V1 — three independent causal LIVE models.

RITARDATARI: ranks numbers by draw gaps only.
FREQUENTI: ranks numbers by recent occurrence frequency only.
DECINE: ranks nine tens groups, uniformly sampling within each group.
CONTROLLO: independent uniformly random 20-of-90 control.

Uses strictly historical BASE draws; no Oro or Extra; never places wagers.
A specialist result counts only when the SAME preview was confirmed delivered
by Telegram before the official target draw. All parameters are frozen.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta

from twin90_advance import MIN_LEAD_SECONDS, ROME, next_concorso, ts

VERSION = "SPECIALIST_LAB_V1"
MODES = ("RITARDATARI", "FREQUENTI", "DECINE", "CONTROLLO")
MAX_FORECASTS = 700


def _root(state):
    lab = state.setdefault("specialist_lab", {})
    if lab.get("version", VERSION) != VERSION:
        raise ValueError("Specialist state version mismatch; refusing to overwrite")
    lab.setdefault("version", VERSION)
    lab.setdefault("forecasts", {})
    lab.setdefault("checked", 0)
    lab.setdefault("not_preannounced", 0)
    lab.setdefault("stats", {})
    for mode in MODES:
        lab["stats"].setdefault(mode, {
            "n": 0, "base_hits": 0, "six_plus": 0, "seven_plus": 0,
            "eight_plus": 0, "decine_abs_error": 0
        })
    lab.setdefault("recent", [])
    return lab


def _seed(key, mode):
    msg = f"{VERSION}|{key}|{mode}".encode("ascii")
    return int.from_bytes(hashlib.sha256(msg).digest()[:8], "big")


def _valid(history):
    if not history:
        raise ValueError("The specialist needs at least one real draw")
    for row in history:
        nums = row["base"]
        if len(nums) != 20 or len(set(nums)) != 20 or any(not 1 <= int(x) <= 90 for x in nums):
            raise ValueError("Invalid real BASE history")


def _weights(history, mode):
    if mode == "CONTROLLO":
        return [1.0] * 90

    if mode == "RITARDATARI":
        # Number of draws since most recent occurrence; unseen = history length.
        gap = [len(history)] * 90
        for i, row in enumerate(reversed(history)):
            for number in row["base"]:
                p = number - 1
                if gap[p] == len(history):
                    gap[p] = i
        return [(1.0 + min(g, 120)) ** 0.55 for g in gap]

    if mode == "FREQUENTI":
        windows = [(10, 0.40), (30, 0.30), (60, 0.20), (100, 0.10)]
        rating = [0.0] * 90
        for length, share in windows:
            window = history[-length:]
            counts = [0] * 90
            for row in window:
                for n in row["base"]:
                    counts[n - 1] += 1
            for i in range(90):
                rating[i] += share * counts[i] / len(window)
        return [math.exp(3.0 * (r - 20 / 90)) for r in rating]

    if mode == "DECINE":
        # Only group occupancy is used. All ten numbers inside a decina
        # share exactly the same selection weight.
        window = history[-60:]
        groups = [0] * 9
        for row in window:
            for n in row["base"]:
                groups[(n - 1) // 10] += 1
        expected = (20.0 / 9.0) * len(window)
        group_weights = [math.exp(0.7 * ((v / expected) - 1.0)) for v in groups]
        return [group_weights[i // 10] for i in range(90)]

    raise ValueError("Unknown specialist " + mode)


def _sample_20(weights, rng):
    # Stable weighted sampling without replacement (no external deps).
    available = list(range(1, 91))
    w = list(weights)
    picked = []
    for _ in range(20):
        threshold = rng.random() * sum(w)
        cumulative = 0.0
        selected = len(w) - 1
        for i, value in enumerate(w):
            cumulative += value
            if threshold < cumulative:
                selected = i
                break
        picked.append(available.pop(selected))
        w.pop(selected)
    return sorted(picked)


def generate(history, key, mode):
    """20 Base numbers, drawn from the preceding real draws ONLY."""
    _valid(history)
    result = _sample_20(_weights(history, mode), random.Random(_seed(key, mode)))
    if len(result) != 20 or len(set(result)) != 20 or any(not 1 <= n <= 90 for n in result):
        raise ValueError("Generated invalid Base forecast")
    return result


def decine_counts(nums):
    counts = [0] * 9
    for x in nums:
        counts[(x - 1) // 10] += 1
    return counts


def score(actual_base, predicted):
    real = set(actual_base)
    chosen = set(predicted)
    groups_real = decine_counts(actual_base)
    groups_virtual = decine_counts(predicted)
    return {
        "hits": len(real & chosen),
        "numbers": sorted(real & chosen),
        "decine_abs_error": sum(abs(a - b) for a, b in zip(groups_real, groups_virtual))
    }


def _valid_preview(rec, key):
    if not rec or not rec.get("sent_at") or rec.get("key") != key:
        return False
    try:
        return (
            ts(rec["created_at"]) <= ts(rec["sent_at"])
            and ts(rec["sent_at"]) < ts(rec["due_at"]) - timedelta(seconds=MIN_LEAD_SECONDS)
            and str(rec["source_key"]) < key
        )
    except (ValueError, KeyError, TypeError):
        return False


def prepare(state, now=None):
    """Attach specialist preview to existing, not-yet-delivered TWIN90 preview.

    Reuses the SAME Telegram message to avoid doubling notifications.
    """
    now = now or datetime.now(ROME)
    lab = _root(state)
    if not state.get("history") or not state.get("latest"):
        return None
    key, due = next_concorso(state["history"][-1])
    if now >= due - timedelta(seconds=MIN_LEAD_SECONDS):
        return None
    if key in lab["forecasts"]:
        return None
    preview = next((x for x in state.get("pending_notifications", [])
                    if x.get("type") == "PREVIEW" and x.get("key") == key), None)
    if preview is None:
        return None
    predictions = {m: generate(state["history"], key, m) for m in MODES}
    rec = {
        "key": key, "source_key": state["latest"],
        "due_at": due.isoformat(), "created_at": now.isoformat(),
        "sent_at": None, "status": "QUEUED",
        "version": VERSION, "base": predictions
    }
    lab["forecasts"][key] = rec
    preview["specialists"] = predictions
    if len(lab["forecasts"]) > MAX_FORECASTS:
        # Prune only old records; lifetime counters remain.
        for stale in sorted(lab["forecasts"])[:-MAX_FORECASTS]:
            lab["forecasts"].pop(stale, None)
    return key


def confirm_sent(state, key, when=None):
    lab = _root(state)
    when = when or datetime.now(ROME)
    record = lab["forecasts"].get(key)
    if not record:
        return False
    record["sent_at"] = when.isoformat()
    record["status"] = "SENT_BEFORE_DRAW" if _valid_preview(record, key) else "LATE"
    return record["status"] == "SENT_BEFORE_DRAW"


def reconcile(state, actual, key):
    """Record results against the previously Telegram-confirmed 20-number sets."""
    lab = _root(state)
    rec = lab["forecasts"].get(key)
    if not _valid_preview(rec, key):
        lab["not_preannounced"] += 1
        if rec:
            rec["status"] = "NO_VALID_PREVIEW"
        return None
    details = {}
    for mode in MODES:
        delta = score(actual["base"], rec["base"][mode])
        stats = lab["stats"][mode]
        stats["n"] += 1
        stats["base_hits"] += delta["hits"]
        stats["six_plus"] += int(delta["hits"] >= 6)
        stats["seven_plus"] += int(delta["hits"] >= 7)
        stats["eight_plus"] += int(delta["hits"] >= 8)
        stats["decine_abs_error"] += delta["decine_abs_error"]
        details[mode] = delta
    lab["checked"] += 1
    rec["status"] = "SCORED_PREANNOUNCED"
    lab["recent"].append({"key": key, "scores": {m: v["hits"] for m, v in details.items()}})
    lab["recent"] = lab["recent"][-50:]
    return {"version": VERSION, "sent_at": rec["sent_at"], "results": details,
            "total": lab["checked"]}


def describe(state):
    lab = _root(state)
    return {
        "version": VERSION,
        "checked": lab["checked"],
        "without_preview": lab["not_preannounced"],
        "models": {name: {
            "n": result["n"],
            "base_mean": round(result["base_hits"] / result["n"], 3) if result["n"] else None,
            "six_plus": result["six_plus"],
            "seven_plus": result["seven_plus"],
            "decine_abs_error_mean": round(result["decine_abs_error"] / result["n"], 3) if result["n"] else None
        } for name, result in lab["stats"].items()}
    }
