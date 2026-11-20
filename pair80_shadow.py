"""PAIR80_SOURCE H1/H2 virtual shadow: no real betting."""
from itertools import combinations
from datetime import datetime

VERSION = "PAIR80_SOURCE_H2_SHADOW_v1"
WARMUP = 80
HORIZON = 2
VIRTUAL_STAKE = 1.0
VIRTUAL_RETURN = 14.0  # hypothetical only; not an official payout


def _counts():
    return {"signals": 0, "h1_checked": 0, "h1_hits": 0,
            "closed_h2": 0, "hits_h2": 0, "interrupted": 0,
            "stakes_virtual": 0.0, "returns_virtual": 0.0}


def _default():
    return {"version": VERSION, "last_key": None, "history": [],
            "active": {}, "finished": [], "totals": _counts(),
            "days": {}, "gaps": 0, "last_updated": None}


def _row(raw):
    day = str(raw["day"])
    draw = int(raw["draw_id"])
    nums = sorted(int(x) for x in raw["nums"])
    if not (1 <= draw <= 288 and len(nums) == 20 and
            len(set(nums)) == 20 and 1 <= nums[0] and nums[-1] <= 90):
        raise ValueError("Concorso Base non valido (20 numeri unici 1..90)")
    datetime.strptime(day, "%Y-%m-%d")
    return {"day": day, "draw_id": draw, "key": f"{day}#{draw:03d}", "nums": nums}


def _consecutive(a, b):
    return bool(a and a["day"] == b["day"] and
                b["draw_id"] == a["draw_id"] + 1)


def ensure(tracker):
    st = tracker.data.get("pair80_shadow")
    if st is None:
        st = _default()
        tracker.data["pair80_shadow"] = st
        tracker.dirty = True
    if st.get("version") != VERSION or not isinstance(st.get("history"), list):
        raise ValueError("Stato PAIR80 sconosciuto; nessuna sovrascrittura automatica")
    return st


def seed(tracker, rows):
    """Warmup da archivio: NON crea segnali retroattivi."""
    st = ensure(tracker)
    if st["last_key"] is not None:
        return "Stato PAIR80 gia inizializzato"
    items = {}
    for raw in rows:
        row = _row(raw)
        old = items.get(row["key"])
        if old and old["nums"] != row["nums"]:
            raise ValueError("Fonti discordanti su " + row["key"])
        items[row["key"]] = row
    if not items:
        return "Nessuna estrazione valida per il warmup"
    ordered = sorted(items.values(), key=lambda r: (r["day"], r["draw_id"]))
    tail = []
    for row in ordered:
        if tail and not _consecutive(tail[-1], row):
            tail = []
        tail.append(row)
        if len(tail) > WARMUP:
            tail.pop(0)
    st["history"] = tail
    st["last_key"] = ordered[-1]["key"]
    st["last_updated"] = st["last_key"]
    tracker.dirty = True
    return f"Warmup {len(tail)}/{WARMUP} | {st['last_key']} | nessun segnale retroattivo"


def _inc(st, day, field, amount=1):
    st["totals"][field] += amount
    st["days"].setdefault(day, _counts())[field] += amount


def _finish(st, sig, status):
    sig["status"] = status
    st["finished"].append(dict(sig))
    if len(st["finished"]) > 2000:
        del st["finished"][:-2000]


def _settle(st, row):
    found = set(row["nums"])
    messages = []
    for ident, sig in list(st["active"].items()):
        step = sig["step"] + 1
        sig["step"] = step
        hit = all(x in found for x in sig["pair"])
        _inc(st, sig["day"], "stakes_virtual", VIRTUAL_STAKE)
        if step == 1:
            _inc(st, sig["day"], "h1_checked")
            if hit:
                _inc(st, sig["day"], "h1_hits")
        if hit:
            _inc(st, sig["day"], "closed_h2")
            _inc(st, sig["day"], "hits_h2")
            _inc(st, sig["day"], "returns_virtual", VIRTUAL_RETURN)
            _finish(st, sig, f"HIT_H{step}")
            del st["active"][ident]
            messages.append(f"PAIR80 {sig['pair'][0]:02d}-{sig['pair'][1]:02d} H{step} HIT")
        elif step >= HORIZON:
            _inc(st, sig["day"], "closed_h2")
            _finish(st, sig, "MISS_H2")
            del st["active"][ident]
            messages.append(f"PAIR80 {sig['pair'][0]:02d}-{sig['pair'][1]:02d} H2 MISS")
    return messages


def _interrupt(st):
    messages = []
    for ident, sig in list(st["active"].items()):
        _inc(st, sig["day"], "interrupted")
        _finish(st, sig, "INTERROTTO_GAP")
        del st["active"][ident]
        messages.append(f"PAIR80 {sig['pair'][0]:02d}-{sig['pair'][1]:02d}: interrotto, fonte non contigua")
    return messages


def _hot(row, dec):
    low = dec * 10 + 1
    return sum(low <= x <= low + 9 for x in row["nums"]) >= 5


def _select_pair(window, dec):
    low = dec * 10 + 1
    choices = tuple(combinations(range(low, low + 10), 2))
    counts = {pair: 0 for pair in choices}
    for row in window:
        members = [x for x in row["nums"] if low <= x <= low+9]
        for pair in combinations(members, 2):
            counts[pair] += 1
    return min(counts, key=lambda pair: (-counts[pair], pair)), max(counts.values())


def process(tracker, raw, create_new=True):
    """Forward-only, same-day contiguous draws, H1/H2 stop at first hit."""
    st = ensure(tracker)
    row = _row(raw)
    if st["last_key"] and row["key"] <= st["last_key"]:
        return {"new": False, "signals": [], "results": [], "gap": False}
    prev = st["history"][-1] if st["history"] else None
    contiguous = _consecutive(prev, row)
    gap = bool(st["last_key"] and not contiguous)
    if gap:
        results = _interrupt(st)
        st["gaps"] += 1
        st["history"] = []
    else:
        results = _settle(st, row) if prev else []
    st["history"].append(row)
    if len(st["history"]) > WARMUP:
        st["history"].pop(0)
    st["last_key"] = row["key"]
    st["last_updated"] = row["key"]
    signals = []
    if create_new and len(st["history"]) >= WARMUP:
        old2, old1, newest = st["history"][-3:]
        for dec in range(9):
            if _hot(old2, dec) and not _hot(old1, dec) and _hot(newest, dec):
                pair, cooc = _select_pair(st["history"], dec)
                ident = f"{row['key']}:D{dec}"
                if ident in st["active"]:
                    continue
                sig = {"id": ident, "day": row["day"], "origin": row["key"],
                       "decina": f"{dec*10+1:02d}-{dec*10+10:02d}",
                       "pair": list(pair), "coocc80": cooc, "step": 0,
                       "status": "H2_PENDING"}
                st["active"][ident] = sig
                _inc(st, row["day"], "signals")
                signals.append(f"PAIR80 SHADOW {row['key']} | decina {sig['decina']} "
                               f"| ambo {pair[0]:02d}-{pair[1]:02d} "
                               f"| co-presenze W80={cooc} | H1/H2")
    tracker.dirty = True
    return {"new": True, "signals": signals, "results": results, "gap": gap}


def report(tracker, day=None):
    st = ensure(tracker)
    d = st["days"].get(day, _counts()) if day else st["totals"]
    n = d["closed_h2"]
    net = d["returns_virtual"] - d["stakes_virtual"]
    return "\n".join([
        "SUPERAMBO3 PAIR80_SOURCE -- SOLO SHADOW",
        "Tutti i metodi precedenti in pausa; storico conservato.",
        f"Warmup: {len(st['history'])}/{WARMUP} consecutivi della stessa giornata",
        f"Ultimo concorso: {st['last_key'] or 'nessuno'}",
        f"Segnali: {d['signals']} | H1: {d['h1_hits']}/{d['h1_checked']}",
        f"H1-H2: {d['hits_h2']}/{n} chiusi ({(100*d['hits_h2']/n if n else 0):.2f}%)",
        f"Saldo virtuale (incasso ipotetico): EUR {net:+.2f}",
        f"Pendenti: {len(st['active'])} | Interrotti: {d['interrupted']} | Gap: {st['gaps']}",
        "Nessuna puntata reale. Nessuna garanzia di vincita."
    ])


def recent(tracker):
    st = ensure(tracker)
    lines = ["PAIR80 ultimi segnali SHADOW:"]
    for sig in st["finished"][-8:] + list(st["active"].values())[-4:]:
        lines.append(f"{sig['origin']} [{sig['decina']}] {sig['pair'][0]:02d}-{sig['pair'][1]:02d} {sig['status']}")
    return "\n".join(lines) if len(lines) > 1 else "Nessun segnale registrato"
