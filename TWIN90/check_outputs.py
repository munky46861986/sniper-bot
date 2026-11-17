"""Controllo delle simulazioni TWIN90: file CSV, Base/Oro/Extra e righe."""
import csv
import sys
from pathlib import Path

def verify(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 288:
        raise ValueError(f"{path}: righe {len(rows)} invece di 288")
    days = {r["date"] for r in rows}
    if len(days) != 1:
        raise ValueError(f"{path}: attese estrazioni di una sola giornata")
    for i, r in enumerate(rows, start=1):
        if int(r["draw"]) != i:
            raise ValueError(f"{path}: concorso fuori sequenza {i}")
        base = [int(v) for v in r["base"].split(".")]
        extra = [int(v) for v in r["extra"].split(".")]
        oro = [int(r["oro1"]), int(r["oro2"])]
        if (len(set(base)) != 20 or len(base) != 20 or
            len(set(extra)) != 15 or len(extra) != 15 or
            not set(oro).issubset(base) or oro[0] == oro[1] or
            set(base).intersection(extra) or
            any(not 1 <= n <= 90 for n in base+extra+oro)):
            raise ValueError(f"{path}: concorso non valido {i}")
    return f"{Path(path).name}: {len(rows)} concorsi validi ({next(iter(days))})"

if __name__ == "__main__":
    lines=[verify(p) for p in sys.argv[1:]]
    print("\n".join(lines))
    Path("TWIN90/output/controlli.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
