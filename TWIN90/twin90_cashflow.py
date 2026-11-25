"""Virtual cash-flow audit of prepublished Superambo MULTI signals.

Two fixed 1 EUR-per-pair strategies:
 FULL5: every selected pair at all five draws;
 STOP1: same pairs, stop after first draw with >=1 winning pair.
The payout assumption is 14 EUR gross per 1 EUR winning pair.
Control has the exact same number of pairs and follows its own stop rule.
No stakes, payouts or gambling actions are sent to any external provider.
Older, already published signals are labelled REPLAY, not FORWARD evidence.
"""
from __future__ import annotations

from datetime import date, timedelta

from twin90_fusion import MODES

VERSION = "SUPERAMBO_CASHFLOW_SHADOW_V1"
POLICIES = ("FULL5", "STOP1")
COHORTS = ("REPLAY", "FORWARD")
SIZES = ("2", "3", "5")
STAKE_EUR = 1
GROSS_MULTIPLIER = 14
HORIZON = 5


def _balance():
    return {"spent_eur": 0, "gross_eur": 0, "net_eur": 0,
            "control_spent_eur": 0, "control_gross_eur": 0,
            "control_net_eur": 0}


def _stats():
    return {mode: {size: {cohort: {policy: dict(
        _balance(), signals=0, positive_signals=0,
        control_positive_signals=0) for policy in POLICIES}
        for cohort in COHORTS} for size in SIZES} for mode in MODES}


def fresh():
    return {"version": VERSION, "initialized": False,
            "processed_keys": [], "replayed_signals": 0,
            "forward_signals": 0, "recent": [],
            "stats": _stats(), "daily": {}, "weekly": {}}


def root(state):
    lab = state.setdefault("superambo_cashflow", fresh())
    if lab.get("version") != VERSION:
        raise ValueError("Cashflow version mismatch; refusing to reset")
    return lab


def _record_day(key, h):
    day, draw = key.split("#")
    number = int(draw)
    if not 1 <= number <= 288 or not 1 <= h <= HORIZON:
        raise ValueError("Invalid draw number or horizon")
    return date.fromisoformat(day) + timedelta(days=(number - 1 + h - 1) // 288)


def _apply(target, spent, gross, ctrl_spent, ctrl_gross):
    target["spent_eur"] += spent
    target["gross_eur"] += gross
    target["net_eur"] += gross - spent
    target["control_spent_eur"] += ctrl_spent
    target["control_gross_eur"] += ctrl_gross
    target["control_net_eur"] += ctrl_gross - ctrl_spent


def _valid(record):
    modes = record.get("modes")
    if not isinstance(modes, dict) or not modes:
        return False
    try:
        for mode, variants in modes.items():
            if mode not in MODES or not isinstance(variants, dict):
                return False
            for size, item in variants.items():
                if size not in SIZES:
                    return False
                pairs = item["pairs"]
                if not isinstance(pairs, list) or not 1 <= len(pairs) <= int(size):
                    return False
                for p in pairs:
                    if (not isinstance(p, list) or len(p) != 2 or
                        type(p[0]) is not int or type(p[1]) is not int or
                        not (1 <= p[0] < p[1] <= 90)):
                        return False
                for field in ("hits", "control_hits"):
                    hits = item[field]
                    if (not isinstance(hits, list) or len(hits) != HORIZON or
                        any(type(n) is not int or n < 0 or n > len(pairs)
                            for n in hits)):
                        return False
        return True
    except (TypeError, KeyError, ValueError):
        return False


def refresh(state):
    """Idempotent import of finalized, acknowledged H1-H5 MULTI records.

    The first call imports existing completed signals as REPLAY. Later cases
    are FORWARD. Consecutive verified observations were guaranteed upstream.
    """
    lab = root(state)
    multi = state.get("superambo_multi") or {}
    source = multi.get("recent") or []
    first = not lab["initialized"]
    seen = set(lab["processed_keys"])
    messages = []
    for record in source:
        key = record.get("key")
        if not key or key in seen or not _valid(record):
            continue
        cohort = "REPLAY" if first else "FORWARD"
        entry = {"key": key, "cohort": cohort, "modes": {}}
        for mode, variants in record["modes"].items():
            entry["modes"][mode] = {}
            for size, item in variants.items():
                n_pairs = len(item["pairs"])
                entry["modes"][mode][size] = {}
                for policy in POLICIES:
                    amounts = _balance()
                    exp_live = True
                    ctrl_live = True
                    for h in range(1, HORIZON + 1):
                        winning = item["hits"][h - 1]
                        ctrl_winning = item["control_hits"][h - 1]
                        exp_bet = policy == "FULL5" or exp_live
                        ctrl_bet = policy == "FULL5" or ctrl_live
                        spent = n_pairs * STAKE_EUR if exp_bet else 0
                        gross = winning * STAKE_EUR * GROSS_MULTIPLIER if exp_bet else 0
                        ctrl_spent = n_pairs * STAKE_EUR if ctrl_bet else 0
                        ctrl_gross = (ctrl_winning * STAKE_EUR * GROSS_MULTIPLIER
                                      if ctrl_bet else 0)
                        _apply(amounts, spent, gross, ctrl_spent, ctrl_gross)
                        if exp_bet and winning:
                            exp_live = False
                        if ctrl_bet and ctrl_winning:
                            ctrl_live = False
                        day = _record_day(key, h)
                        period_key = "|".join((mode, size, cohort, policy))
                        weekly = day.isocalendar()
                        week_key = f"{weekly.year}-W{weekly.week:02d}"
                        for ledger, period in ((lab["daily"], day.isoformat()),
                                               (lab["weekly"], week_key)):
                            row = ledger.setdefault(period, {}).setdefault(period_key,
                                                                           _balance())
                            _apply(row, spent, gross, ctrl_spent, ctrl_gross)
                    totals = lab["stats"][mode][size][cohort][policy]
                    _apply(totals, amounts["spent_eur"], amounts["gross_eur"],
                           amounts["control_spent_eur"], amounts["control_gross_eur"])
                    totals["signals"] += 1
                    totals["positive_signals"] += int(amounts["net_eur"] > 0)
                    totals["control_positive_signals"] += int(
                        amounts["control_net_eur"] > 0)
                    entry["modes"][mode][size][policy] = amounts
        lab["processed_keys"].append(key)
        seen.add(key)
        if cohort == "REPLAY":
            lab["replayed_signals"] += 1
        else:
            lab["forward_signals"] += 1
            messages.append(entry)
        lab["recent"].append(entry)
        lab["recent"] = lab["recent"][-200:]
    lab["initialized"] = True
    return messages


def describe(state):
    lab = root(state)
    return {"version": VERSION, "execution": "SHADOW_ONLY_NO_WAGERS",
            "stake_eur_per_pair": STAKE_EUR,
            "gross_multiplier": GROSS_MULTIPLIER,
            "replayed_signals": lab["replayed_signals"],
            "forward_signals": lab["forward_signals"],
            "stats": lab["stats"],
            "daily": lab["daily"],
            "weekly": lab["weekly"]}


def format_extra(message):
    records = message.get("superambo_cashflow_results") or []
    if not records:
        return ""
    lines = ["", "💶 SALDO VIRTUALE FUSION — 1€ PER AMBO",
             "FULL5=5 colpi; STOP1=stop dopo primo ambo. Lordo 14x."]
    for rec in records:
        lines.append(f"Concorso {rec['key']} (solo SHADOW)")
        for mode, variants in rec["modes"].items():
            label = "DECINE" if mode == MODES[0] else "HYBRID"
            for size, options in variants.items():
                a = options["FULL5"]["net_eur"]
                b = options["STOP1"]["net_eur"]
                lines.append(f"{label} MULTI-{size}: FULL5 {a:+d}€ | STOP1 {b:+d}€")
    lines.append("Saldi teorici, nessuna giocata reale.")
    return "\n".join(lines)
