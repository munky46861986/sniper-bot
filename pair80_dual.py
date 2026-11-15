"""Superambo3: PAIR80 SINGOLO e DOPPIO LIVE SHADOW, senza puntate reali."""
from itertools import combinations
from datetime import datetime

VERSION = "PAIR80_DUAL_H2_SHADOW_v1"
STATE_KEY = "pair80_dual_shadow"
MODES = ("SINGOLO", "DOPPIO")
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
            "active": {}, "finished": [],
            "totals": {mode: _counts() for mode in MODES},
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
    st = tracker.data.get(STATE_KEY)
    if st is None:
        st = _default()
        tracker.data[STATE_KEY] = st
        tracker.dirty = True
    if (st.get("version") != VERSION or not isinstance(st.get("history"), list)
            or not isinstance(st.get("totals"), dict)
            or any(m not in st["totals"] for m in MODES)):
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


def _inc(st, day, mode, field, amount=1):
    st["totals"][mode][field] += amount
    daily = st["days"].setdefault(day, {m: _counts() for m in MODES})
    daily.setdefault(mode, _counts())[field] += amount

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
        mode = sig["method"]
        hit = all(x in found for x in sig["pair"])
        _inc(st, sig["day"], mode, "stakes_virtual", VIRTUAL_STAKE)
        if step == 1:
            _inc(st, sig["day"], mode, "h1_checked")
            if hit:
                _inc(st, sig["day"], mode, "h1_hits")
        prefix = f'{mode} [{sig["decina"]}] {sig["pair"][0]:02d}-{sig["pair"][1]:02d}'
        if hit:
            _inc(st, sig["day"], mode, "closed_h2")
            _inc(st, sig["day"], mode, "hits_h2")
            _inc(st, sig["day"], mode, "returns_virtual", VIRTUAL_RETURN)
            _finish(st, sig, f"HIT_H{step}")
            del st["active"][ident]
            messages.append(f"✅ {prefix} H{step}: AMBO HIT")
        elif step >= HORIZON:
            _inc(st, sig["day"], mode, "closed_h2")
            _finish(st, sig, "MISS_H2")
            del st["active"][ident]
            messages.append(f"❌ {prefix} H2: STOP senza ambo")
        else:
            messages.append(f"⏳ {prefix} H1: MISS, in verifica H2")
    return messages


def _interrupt(st):
    messages = []
    for ident, sig in list(st["active"].items()):
        _inc(st, sig["day"], sig["method"], "interrupted")
        _finish(st, sig, "INTERROTTO_GAP")
        del st["active"][ident]
        messages.append(f"⚠️ {sig['method']} [{sig['decina']}] "
                        f"{sig['pair'][0]:02d}-{sig['pair'][1]:02d}: interrotto, fonte non contigua")
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
    """Solo nuovi concorsi, W80 nella stessa giornata, due metodi indipendenti."""
    st = ensure(tracker)
    row = _row(raw)
    if st["last_key"] and row["key"] <= st["last_key"]:
        if row["key"] == st["last_key"] and st["history"] and st["history"][-1]["nums"] != row["nums"]:
            raise ValueError("Concorso gia visto con Base discordante: " + row["key"])
        return {"new": False, "signals": [], "results": [], "gap": False}
    prev = st["history"][-1] if st["history"] else None
    gap = bool(st["last_key"] and not _consecutive(prev, row))
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
    if create_new and len(st["history"]) == WARMUP:
        a, b, c = st["history"][-3:]
        for dec in range(9):
            if not _hot(c, dec):
                continue
            double = _hot(a, dec) and not _hot(b, dec)
            pair, cooc = _select_pair(st["history"], dec)
            for mode in MODES:
                if mode == "DOPPIO" and not double:
                    continue
                ident = f'{row["key"]}:{mode}:D{dec}'
                sig = {"id": ident, "method": mode, "day": row["day"],
                       "origin": row["key"],
                       "decina": f"{dec*10+1:02d}-{dec*10+10:02d}",
                       "pair": list(pair), "coocc80": cooc, "step": 0,
                       "status": "PENDING_H1_H2"}
                st["active"][ident] = sig
                _inc(st, row["day"], mode, "signals")
                signals.append(f'🎯 {mode} {row["key"]} | decina {sig["decina"]} '
                               f'| ambo {pair[0]:02d}-{pair[1]:02d} '
                               f'| W80={cooc} | H1/H2')
    tracker.dirty = True
    return {"new": True, "signals": signals, "results": results, "gap": gap}

def report(tracker, day=None, mode=None):
    st = ensure(tracker)
    modes = [mode] if mode in MODES else list(MODES)
    lines = ["📊 SUPERAMBO3 - PAIR80 SINGOLO + DOPPIO | LIVE SHADOW",
             "Altri metodi in pausa; codice e storico conservati.",
             f'Warmup: {len(st["history"])}/{WARMUP} consecutivi nella giornata',
             f'Ultimo concorso: {st["last_key"] or "nessuno"}', ""]
    for m in modes:
        d = st["days"].get(day, {}).get(m, _counts()) if day else st["totals"][m]
        n = d["closed_h2"]
        net = d["returns_virtual"] - d["stakes_virtual"]
        pending = sum(s["method"] == m for s in st["active"].values())
        lines.extend([
            f'{m}: segnali {d["signals"]} | H1: {d["h1_hits"]}/{d["h1_checked"]}',
            f'H1-H2: {d["hits_h2"]}/{n} chiusi ({100*d["hits_h2"]/n if n else 0:.2f}%)',
            f'Pendenti: {pending} | Interrotti: {d["interrupted"]}',
            f'Saldo virtuale (premio ipotetico): EUR {net:+.2f}', ""])
    lines.extend([f'Gap fonte: {st["gaps"]}',
                  "Ogni DOPPIO e' anche SINGOLO: conteggi separati.",
                  "Nessuna giocata reale; rendimento futuro non garantito."])
    return "\n".join(lines)

def recent(tracker, mode=None):
    st = ensure(tracker)
    selected = st["finished"][-30:] + list(st["active"].values())
    if mode in MODES:
        selected = [sig for sig in selected if sig["method"] == mode]
    lines = ["Ultimi segnali PAIR80 LIVE SHADOW:"]
    for sig in selected[-15:]:
        lines.append(f'{sig["method"]} {sig["origin"]} [{sig["decina"]}] '
                     f'{sig["pair"][0]:02d}-{sig["pair"][1]:02d} {sig["status"]}')
    return "\n".join(lines) if len(lines) > 1 else "Nessun segnale registrato"

