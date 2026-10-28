#!/usr/bin/env python3
"""V121 H7/H8: monitor didattico read-only per una ventina fissa.
Nessuna giocata, nessun accesso online, nessun retraining del modello congelato.
La ricorrenza osservata NON dimostra capacità predittiva.
"""
import os

V121_ZONE_NOTIFY = os.getenv("V121_ZONE_NOTIFY", "1").strip().lower() not in {"0","false","no","off"}
try:
    V121_ZONE_START = int(os.getenv("V121_ZONE_START_H", "7"))
except (ValueError, TypeError):
    V121_ZONE_START = 7
if V121_ZONE_START not in (7, 8):
    V121_ZONE_START = 7

BASELINE = 20.0 / 90.0
PRIOR_STRENGTH = 40.0
ZONE_VALUE_NAMES = ("BASSA_01_30","MEDIA_31_60","ALTA_61_90")
ZONE_POSITION_NAMES = ("PRIMI_7","CENTRO_7","FINALI_6")


def _valid20(seq):
    try:
        a = [int(x) for x in seq]
    except (ValueError, TypeError):
        return None
    if len(a) != 20 or len(set(a)) != 20 or not all(1 <= n <= 90 for n in a):
        return None
    return a


def _tally():
    return {"shown": 0, "hits": 0, "winning_shown": 0, "winning_hits": 0}


def _position_group(index):
    return ZONE_POSITION_NAMES[0 if index < 7 else 1 if index < 14 else 2]


def _value_group(num):
    return ZONE_VALUE_NAMES[0 if num <= 30 else 1 if num <= 60 else 2]


class V121ZoneMonitor:
    """Un ciclo t0 -> H1..H7/H8..primo >=7, con memoria anti-duplicato.

    Apprendimento descrittivo: registra solo esiti già osservati, calcola
    percentuali per candidato e classifica i numeri con una stima smussata.
    NON riscrive la previsione V121 né modifica le altre strategie.
    """
    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        self.active = dict(d["active"]) if isinstance(d.get("active"), dict) else None
        self.completed = max(0, int(d.get("completed") or 0))
        self.aborted = max(0, int(d.get("aborted") or 0))
        self.checked = max(0, int(d.get("checked") or 0))
        self.winning_steps = [int(n) for n in (d.get("winning_steps") or []) if 1 <= int(n) <= 50000][-300:]
        self.zone_values = {name: _tally() for name in ZONE_VALUE_NAMES}
        self.zone_positions = {name: _tally() for name in ZONE_POSITION_NAMES}
        for table, saved in ((self.zone_values,d.get("zone_values")), (self.zone_positions,d.get("zone_positions"))):
            if isinstance(saved, dict):
                for name in table:
                    if isinstance(saved.get(name), dict):
                        for field in table[name]:
                            table[name][field] = max(0,int(saved[name].get(field) or 0))
        self.numbers = {}
        for k,v in (d.get("numbers") or {}).items():
            if str(k).isdigit() and 1 <= int(k) <= 90 and isinstance(v,dict):
                self.numbers[str(int(k))] = {
                    "shown": max(0,int(v.get("shown") or 0)),
                    "hits": max(0,int(v.get("hits") or 0)),
                }
        self.closed = [dict(v) for v in (d.get("closed") or []) if isinstance(v,dict)][-75:]
        self.last_note = str(d.get("last_note") or "")[:180]

    def dump(self):
        return {
            "version": "V121_H7_H8_ZONE_LEARN_SHADOW_V1",
            "active": dict(self.active) if self.active else None,
            "completed": self.completed, "aborted": self.aborted,
            "checked": self.checked,
            "winning_steps": self.winning_steps[-300:],
            "zone_values": self.zone_values,
            "zone_positions": self.zone_positions,
            "numbers": self.numbers,
            "closed": self.closed[-75:],
            "last_note": self.last_note,
            "config_new_cycles_start_h": V121_ZONE_START,
        }

    def arm(self, origin_key, predicted):
        """Congela la prossima ventina, solo se non esiste un ciclo attivo."""
        if self.active or not origin_key:
            return False
        nums = _valid20(predicted)
        if not nums:
            self.last_note = "Ventina non valida; ciclo non avviato"
            return False
        nums.sort()
        self.active = {
            "origin_key": str(origin_key),
            "last_key": str(origin_key),
            "base_numbers": nums,
            "h": 0,
            "start_h": V121_ZONE_START,
            "checked": 0,
            "best_h": 0,
        }
        self.last_note = f"Ciclo avviato {origin_key}; verifica da H{V121_ZONE_START}"
        return True

    def _stop_incomplete(self, reason):
        p = dict(self.active) if self.active else {}
        self.active = None
        self.aborted += 1
        self.last_note = "Ciclo interrotto: " + str(reason)[:135]
        self.closed.append({"origin_key":p.get("origin_key"),"status":"DATI_MANCANTI",
                            "h":p.get("h",0),"reason":reason})
        self.closed = self.closed[-75:]
        return {"kind":"MISSING","origin":p.get("origin_key"),
                "h":p.get("h",0),"reason":str(reason)[:135]}

    def observe(self, row, consecutive):
        """Aggiorna solo su concorsi reali contigui; niente salto di H."""
        p = self.active
        if not p:
            return None
        key = str(row.get("key") or "")
        if not key or key <= str(p.get("last_key") or ""):
            return None
        if not consecutive:
            return self._stop_incomplete(f"gap fra {p.get('last_key')} e {key}")
        actual = _valid20(row.get("nums") or [])
        if actual is None:
            return self._stop_incomplete("estrazione Base con numeri invalidi")
        p["h"] = int(p.get("h",0))+1
        p["last_key"] = key
        actual_set = set(actual)
        forecast = p["base_numbers"]
        matched = sorted(actual_set.intersection(forecast))
        hits = len(matched)
        p["best_h"] = max(int(p.get("best_h",0)),hits)
        if p["h"] < int(p["start_h"]):
            return None
        p["checked"] = int(p.get("checked",0))+1
        self.checked += 1
        winning = hits >= 7
        values = {k:[] for k in ZONE_VALUE_NAMES}
        positions = {k:[] for k in ZONE_POSITION_NAMES}
        for idx,n in enumerate(forecast):
            z1 = _value_group(n); z2 = _position_group(idx)
            found = n in actual_set
            for dest,zone in ((values,z1),(positions,z2)):
                if found:
                    dest[zone].append(n)
            for table, zone in ((self.zone_values,z1),(self.zone_positions,z2)):
                table[zone]["shown"] += 1
                table[zone]["hits"] += int(found)
                if winning:
                    table[zone]["winning_shown"] += 1
                    table[zone]["winning_hits"] += int(found)
            count = self.numbers.setdefault(str(n),{"shown":0,"hits":0})
            count["shown"] += 1
            count["hits"] += int(found)
        event = {
            "kind":"HIT7" if winning else "CHECK",
            "origin":p["origin_key"],"target":key,
            "h":p["h"],"start_h":p["start_h"],"hits":hits,
            "matched":matched, "values":values, "positions":positions,
            "checked":p["checked"],"cycles_completed":self.completed,
        }
        if winning:
            self.completed += 1
            self.winning_steps.append(p["h"])
            self.winning_steps = self.winning_steps[-300:]
            self.closed.append({"origin_key":p["origin_key"],"target_key":key,
                                "status":"HIT7","h":p["h"],"hits":hits,
                                "start_h":p["start_h"],"checked":p["checked"],
                                "matched":matched,"values":values,"positions":positions})
            self.closed = self.closed[-75:]
            self.active = None
            event["cycles_completed"] = self.completed
            self.last_note = f"Chiuso 7+ a H{p['h']} ({key}); {self.completed} cicli completati"
        return event

    def _percent(self, hits, shown):
        return f"{100*hits/shown:.1f}%" if shown else "n.d."

    def _learn_top(self, limit=6):
        candidates = []
        for number, count in self.numbers.items():
            shown = int(count["shown"]); hits = int(count["hits"])
            if shown < 10:
                continue
            smooth = (hits + BASELINE*PRIOR_STRENGTH)/(shown+PRIOR_STRENGTH)
            candidates.append((smooth,shown,int(number)))
        candidates.sort(key=lambda x:(-x[0],-x[1],x[2]))
        return candidates[:limit]

    def report_lines(self):
        p = self.active
        title = f"🔎 V121 ZONE H{V121_ZONE_START} — SOLO SHADOW"
        lines = [title,
                 (f"Ventina fissata {p['origin_key']}: H{p['h']} | verifiche H>=H{p['start_h']}: {p['checked']}"
                  if p else "Nessuna ventina attiva; si avvia alla prossima previsione fresca."),
                 f"Cicli chiusi con 7+: {self.completed} | interrotti per dati mancanti: {self.aborted} | verifiche: {self.checked}"]
        for label,table in (("Valore",self.zone_values),("Posizione",self.zone_positions)):
            pieces = [f"{z.split('_')[0]} {self._percent(d['hits'],d['shown'])} ({d['hits']}/{d['shown']})"
                      for z,d in table.items()]
            lines.append(label+": "+" | ".join(pieces))
        winners=self._learn_top()
        if winners:
            lines.append("Numeri più presenti (stima regolarizzata; non probabilità futura): "+
                         " ".join(f"{n:02d}={100*rate:.1f}%[n={count}]" for rate,count,n in winners))
        if self.winning_steps:
            lines.append(f"Attesa media al primo 7+ dopo il gate: {sum(self.winning_steps)/len(self.winning_steps):.1f} estrazioni dall'origine; max H{max(self.winning_steps)}")
        lines.append("⚠️ Fasce e numeri descrivono il passato: non modificano V121 e non garantiscono 7+.")
        return lines

    def format_event(self, event):
        if event is None:
            return []
        if event["kind"]=="MISSING":
            return ["⚠️ V121 ZONE: ciclo sospeso perché mancava continuità delle estrazioni: "+event["reason"]]
        h=event["h"]
        lines=[f"🧠 V121 ZONE {event['kind']} | {event['target']} H{h}: {event['hits']}/20 (partenza H{event['start_h']})"]
        lines.append("HIT: "+" ".join(f"{n:02d}" for n in event["matched"]) if event["matched"] else "HIT: nessuno")
        lines.append("Valore: "+", ".join(f"{z.split('_')[0]} {len(ns)}" for z,ns in event["values"].items()))
        lines.append("Posizione: "+", ".join(f"{z.split('_')[0]} {len(ns)}" for z,ns in event["positions"].items()))
        if event["kind"]=="HIT7":
            lines.append(f"✅ Primo 7+ dal controllo H{event['start_h']}, raggiunto al colpo H{h}; ciclo chiuso.")
            lines += self.report_lines()[2:5]
        return lines
