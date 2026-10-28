#!/usr/bin/env python3
"""V212: inspect the verified public APK's Home scrolling/navigation definitions.
Static only; no authenticated calls, API workarounds, WebView injection or games.
"""
from pathlib import Path
from hashlib import sha256
import zipfile, re, json

APK=Path("MyLotteries-v194.apk")
OUT=Path("v212_risultati"); OUT.mkdir(exist_ok=True)
EXPECTED="857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a"
if not APK.exists():
    raise SystemExit("The verified APK was not downloaded")
if sha256(APK.read_bytes()).hexdigest()!=EXPECTED:
    raise SystemExit("Unexpected APK hash: refusing analysis")
NEEDLES=["newAppContainer","deferScrollToHash","scrollToElementsNotification",
         "estrazione_diecielotto","estrazione10elotto","Segui l",
         "overflow-y","overflowY","touchmove","wheel","/home","/estrazioni"]
matches=[]
with zipfile.ZipFile(APK) as z:
    names=[x for x in z.namelist() if x.startswith("assets/www/") and x.endswith((".js",".css"))]
    for filename in names:
        # This is a bounded, literal search; never execute the app code.
        data=z.read(filename).decode("utf-8",errors="replace")
        for term in NEEDLES:
            found=list(re.finditer(re.escape(term), data, re.IGNORECASE))
            if not found: continue
            relevant=filename.endswith(".css") or filename.endswith("main.79046245.js")
            if not relevant and term in ("overflow-y","overflowY","touchmove","wheel","/home"): continue
            for hit in found[:(12 if relevant else 3)]:
                left=max(0,hit.start()-125);right=min(len(data),hit.end()+220)
                excerpt=data[left:right].replace("\n"," ")
                matches.append(dict(file=filename,term=term,offset=hit.start(),
                                    excerpt=excerpt))
report={"version":212,"file_count":len(names),"total_hits":len(matches),
        "source_sha256":EXPECTED,"matched_files":sorted({x["file"] for x in matches}),
        "matches":matches}
(OUT/"scroll_sources.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
lines=["# V212 — Indizi statici del router e contenitore Home",
       "Analisi senza esecuzione di JavaScript e senza accesso a servizi protetti.",
       f"APK SHA-256 verificato: `{EXPECTED}`.",
       f"File JS/CSS analizzati: {len(names)}. Estratti selezionati: {len(matches)}.",
       "",
       "Attenzione: le occorrenze testuali da sole non dimostrano che la diretta sia raggiungibile.\n"]
for x in matches[:130]:
    lines.append(f'## {x["term"]} — {x["file"]} (offset {x["offset"]})')
    lines.append("```text")
    lines.append(x["excerpt"].replace("```","` ` `"))
    lines.append("```")
(OUT/"scroll_sources.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k!="matches"},ensure_ascii=False,indent=2))
