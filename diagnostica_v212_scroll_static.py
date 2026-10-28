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

# Second pass: short, targeted neighborhoods for the Home card's ordinary UI controls.
with zipfile.ZipFile(APK) as z:
    sources={}
    for name in ("assets/www/main.79046245.js","assets/www/main.c6798567.css"):
        sources[name]=z.read(name).decode("utf-8",errors="replace")
patterns=("new-app-container","homeCardsOpened","isCollapsed",
          "toggleCard","estrazione_diecielotto","estrazione10elotto",
          "deferScrollToHash","preventScrolling","collapsed:!0")
detail=["# V212 — Contesto specifico dei controlli Home","Solo estratti statici limitati dall'APK verificato.",""]
for name,source in sources.items():
    for term in patterns:
        hits=list(re.finditer(re.escape(term),source,re.IGNORECASE))
        for hit in hits[:(5 if name.endswith(".js") else 8)]:
            before=max(0,hit.start()-420)
            after=min(len(source),hit.end()+520)
            detail.append(f"## {name} — {term}, offset {hit.start()}")
            detail.append("```text")
            detail.append(source[before:after].replace("```","` ` `"))
            detail.append("```")
(OUT/"home_card_context.md").write_text("\n".join(detail),encoding="utf-8")
print("V212 targeted context sections:",sum(line.startswith("## ") for line in detail))

# V212c: independent, static tracing of the 10eLotto public CTA's internal target.
traces=[]
targets=("estrazione5minuti","estrazioniFai","btn_seelive","OPENSECTION",
         "ESTRAZIONEFREQUENTE-GET-CURRENT-EXTRACTION","numberToExtract")
with zipfile.ZipFile(APK) as z:
    for filename in names:
        if not filename.endswith(".js"): continue
        source=z.read(filename).decode("utf-8",errors="replace")
        for term in targets:
            hits=list(re.finditer(re.escape(term),source,re.IGNORECASE))
            for hit in hits[:(18 if filename.endswith("main.79046245.js") else 4)]:
                traces.append({"file":filename,"term":term,"offset":hit.start(),
                               "context":source[max(0,hit.start()-310):
                                                min(len(source),hit.end()+440)].replace("\n"," ")})
(OUT/"cta_route_traces.json").write_text(
    json.dumps({"version":"212c","traces":traces},ensure_ascii=False,indent=2),encoding="utf8")
render=["# V212c — destinazione interna del pulsante pubblico 10eLotto",
        "Solo analisi statica dell'APK ufficiale già verificato.",
        "Nessuna interazione con il servizio o l'account utente.",
        ""]
for t in traces[:170]:
    render += [f'## {t["term"]} — {t["file"]} @ {t["offset"]}',
               "```text",t["context"].replace("```","` ` `"),"```"]
(OUT/"cta_route_traces.md").write_text("\n".join(render),encoding="utf8")
print(json.dumps({"cta_target_traces":len(traces),
                  "matching_files":sorted({t["file"] for t in traces})},
                 ensure_ascii=False))
