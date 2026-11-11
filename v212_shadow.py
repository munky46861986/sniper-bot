"""V212 AMBO SELECTOR — SOLO SHADOW, no real bets.

Selection is forward-only and frozen: coefficients fitted on 2025 Jan-Apr,
threshold from 2025 May-Jun. 2026 was used only for external diagnostics.
Source: 20 BASE numbers sorted ascending, not temporal extraction order.
One selected pair per origin at most. H1/H4 are independent virtual ledgers.
"""
from collections import Counter
import math

V212_RULES = {'A': (3, 19, 60), 'B': (7, 12, 18), 'C': (1, 7, 15)}
V212_FEATURES = ('is_A', 'is_C', 'distance', 'pair_sum', 'freq5_min',
                 'freq15_min', 'freq80_min', 'freq80_max', 'cooc80')
V212_MEAN = (0.21954895032217833, 0.13604240282685512, 23.40443774683018,
             77.24220536271045, 1.4427353980461441, 3.2524423196840573,
             16.467054666389522, 20.67085844938682, 4.758989815007275)
V212_STD = (0.4139410691567194, 0.34283358566504357, 17.60513340920406,
            26.893214082121652, 0.5813518606655848, 1.1924909522159752,
            2.9648403240101273, 3.160528897674165, 1.9068708535150538)
V212_COEF = (-0.08636320096871894, 0.06802789953034293,
             0.07445969751604467, 0.06121079289022128,
             -0.07142019500248653, -0.01597165927652811,
             0.010319886828820629, 0.022005524841148816,
             0.02275810476716223)
V212_INTERCEPT = -2.9216404780471508
V212_CUTOFF = 0.053757460102880225
V212_RETURN = 14.0  # hypothetical total return per €1 winning stake
V212_STAKE = 1.0
V212_WINDOW = 80


def _counts():
    return {'signals': 0, 'h1_checked': 0, 'h1_hits': 0,
            'h1_cost': 0.0, 'h1_return': 0.0, 'h4_closed': 0,
            'h4_hits': 0, 'h4_cost': 0.0, 'h4_return': 0.0,
            'interrupted': 0, 'skipped': 0, 'eligible': 0}


def v212_ensure(tracker):
    data = tracker.data
    if not isinstance(data.get('v212_shadow'), dict):
        data['v212_shadow'] = {'schema': 1, 'version': 'V212_SHADOW_2026_11',
              'last_key': None, 'active': {}, 'finished': [], 'recent': [],
              'totals': _counts(), 'days': {}, 'gap_count': 0, 'warmup': 0,
              'latest': None, 'processed': 0}
        tracker.dirty = True
    return data['v212_shadow']


def _add(st, day, field, qty=1):
    for dest in (st['totals'], st['days'].setdefault(day, _counts())):
        dest[field] = dest.get(field, 0) + qty


def _consecutive(x, y):
    """Consecutive rows only; day rollover if final draw ends prior day."""
    try:
        a, b = str(x['day']), str(y['day'])
        i, j = int(x['draw_id']), int(y['draw_id'])
        if a == b:
            return j == i + 1
        return j == 1 and i in (228, 288) and a < b
    except (TypeError, ValueError, KeyError):
        return False


def _recent_window(tracker, current_row):
    history = tracker.data.get('lab_strutture', {}).get('history') or []
    last = history[-V212_WINDOW:]
    if len(last) != V212_WINDOW:
        return []
    if str(last[-1].get('key')) != str(current_row.get('key')):
        return []
    if any(not _consecutive(a, b) for a, b in zip(last, last[1:])):
        return []
    try:
        rows = [tuple(sorted(int(n) for n in h['nums'])) for h in last]
    except (TypeError, ValueError, KeyError):
        return []
    if any(len(set(nums)) != 20 or len(nums) != 20 for nums in rows):
        return []
    return rows


def v212_candidates(window):
    """Read only current and historical BASE; no knowledge of next draw."""
    if len(window) != V212_WINDOW:
        return []
    nums = window[-1]
    frequencies = {}
    for k in (5, 15, 80):
        frequencies[k] = Counter(n for draw in window[-k:] for n in draw)
    occurrences = [set(v) for v in window]
    out = []
    for name, (p, q, limit) in V212_RULES.items():
        a, b = nums[p-1], nums[q-1]
        distance = b - a
        if distance > limit:
            continue
        fa, fb = frequencies[80][a], frequencies[80][b]
        features = (int(name == 'A'), int(name == 'C'), distance, a+b,
                    min(frequencies[5][a], frequencies[5][b]),
                    min(frequencies[15][a], frequencies[15][b]),
                    min(fa, fb), max(fa, fb),
                    sum(a in draw and b in draw for draw in occurrences))
        z = V212_INTERCEPT + sum(weight * (value-mu)/sd for value, mu, sd, weight
                                   in zip(features, V212_MEAN, V212_STD, V212_COEF))
        score = 1/(1+math.exp(-max(-40, min(40, z))))
        out.append({'method': name, 'pair': [a,b], 'distance': distance,
                    'score': round(score, 9)})
    return sorted(out, key=lambda x: (-x['score'], x['method']))


def v212_process(tracker, row, gap=False):
    """Called ONCE after lab_update on every new ABC draw. Doesn't touch ABC."""
    st = v212_ensure(tracker)
    key = str(row.get('key') or f"{row['day']}#{int(row['draw_id']):03d}")
    if st['last_key'] == key:
        return {'signals': [], 'results': [], 'digest': False}
    if st['last_key'] and key <= st['last_key']:
        return {'signals': [], 'results': [], 'digest': False}
    st['last_key'] = key
    st['processed'] += 1
    signals, results = [], []
    if gap:
        st['gap_count'] += 1
        for sid, sig in list(st['active'].items()):
            sig['status'] = 'INTERRUPTED'
            _add(st, sig['day'], 'interrupted')
            st['finished'].append(sig)
            results.append(f"{sig['pair'][0]:02d}-{sig['pair'][1]:02d} INTERROTTO (gap)")
            del st['active'][sid]
    else:
        found = set(int(n) for n in row['nums'])
        for sid, sig in list(st['active'].items()):
            sig['step'] += 1
            hit = all(n in found for n in sig['pair'])
            if sig['step'] == 1:
                sig['h1'] = int(hit)
                _add(st, sig['day'], 'h1_checked')
                _add(st, sig['day'], 'h1_cost', V212_STAKE)
                if hit:
                    _add(st, sig['day'], 'h1_hits')
                    _add(st, sig['day'], 'h1_return', V212_STAKE*V212_RETURN)
            _add(st, sig['day'], 'h4_cost', V212_STAKE)
            if hit or sig['step'] == 4:
                sig['h4'] = int(hit)
                sig['first_hit'] = sig['step'] if hit else None
                sig['status'] = 'CLOSED'
                _add(st, sig['day'], 'h4_closed')
                if hit:
                    _add(st, sig['day'], 'h4_hits')
                    _add(st, sig['day'], 'h4_return', V212_STAKE*V212_RETURN)
                results.append(f"{sig['pair'][0]:02d}-{sig['pair'][1]:02d} "
                               + (f"HIT H{sig['step']}" if hit else 'MISS H4'))
                st['finished'].append(sig)
                del st['active'][sid]
    window = _recent_window(tracker, dict(row, key=key))
    st['warmup'] = len(window)
    if window:
        candidates = v212_candidates(window)
        if candidates:
            _add(st, str(row['day']), 'eligible')
            best = candidates[0]
            if best['score'] >= V212_CUTOFF:
                sid = f'{key}:V212'
                sig = {'id': sid, 'origin_key': key, 'day': str(row['day']),
                       'method': best['method'], 'pair': best['pair'],
                       'distance': best['distance'], 'score': best['score'],
                       'step': 0, 'h1': None, 'h4': None, 'first_hit': None,
                       'status': 'OPEN'}
                st['active'][sid] = sig
                _add(st, str(row['day']), 'signals')
                st['latest'] = dict(sig)
                signals.append(f"{best['method']} {best['pair'][0]:02d}-{best['pair'][1]:02d} "
                               f"score={best['score']:.4f} | H1/H4 SHADOW")
            else:
                _add(st, str(row['day']), 'skipped')
    st['finished'] = st['finished'][-2400:]
    events = ([{'origin': key, 'type': 'result', 'message': x} for x in results] +
              [{'origin': key, 'type': 'signal', 'message': x} for x in signals])
    st['recent'] = (st['recent'] + events)[-60:]
    tracker.dirty = True
    return {'signals': signals, 'results': results, 'digest': st['processed']%24 == 0}


def v212_report(tracker, day=None, recent=False):
    st = v212_ensure(tracker)
    c = st['days'].get(day, _counts()) if day else st['totals']
    h1, h4 = c['h1_checked'], c['h4_closed']
    pct = lambda x,y: f"{100*x/y:.2f}%" if y else 'n.d.'
    rows = ['🧪 V212 — SELEZIONE AMBI | SOLO SHADOW',
        'Modello congelato 2025, 1 coppia max per concorso, nessuna giocata reale.',
        f"Periodo: {day or 'cumulativo'} | origine finale: {st['last_key'] or '-'}",
        f"Segnali: {c['signals']} | opportunita': {c['eligible']} | scartati: {c['skipped']}",
        f"H1: {c['h1_hits']}/{h1} ({pct(c['h1_hits'], h1)}) | virtuale €{c['h1_return']-c['h1_cost']:+.2f}",
        f"H4: {c['h4_hits']}/{h4} ({pct(c['h4_hits'], h4)}) | virtuale €{c['h4_return']-c['h4_cost']:+.2f}",
        f"Interrotti: {c['interrupted']} | attivi: {len(st['active'])} | gap: {st['gap_count']}",
        f"Ultima coppia: {_latest_label(st.get('latest'))}",
        'Quota simulata 14x, €1/colpo; modello NON profittevole nel backtest 2026.']
    if recent:
        rows += ['', 'Ultimi eventi:']
        rows += [f"{x['origin']} {x['message']}" for x in st['recent'][-10:]]
    return '\n'.join(rows)


def _latest_label(sig):
    if not sig:
        return 'nessuna'
    a,b = sig['pair']
    return f"{sig['origin_key']} {sig['method']} {a:02d}-{b:02d} (score {sig['score']:.4f})"
