# LOTTO TWIN90 LIVE

Osservatore automatico in modalità shadow: nessuna giocata, nessun ordine e nessun messaggio Telegram.
Non modifica PAIR80/Superambo3.

**Workflow:** TWIN90 - osservazione LIVE ogni 5 minuti.
**Frequenza prevista:** :02, :07, :12 ... di ogni ora UTC. GitHub Actions può ritardare o saltare i run programmati.
**Fonte:** risultati pubblici Lottologia, Base/Oro/Doppio Oro/Extra.
**Codice:** branch main, cartella TWIN90.
**Stato:** branch separato twin90-live-state, file twin90_live_state.json.

Al primo controllo usa le ultime estrazioni REALI solo per inizializzare la memoria; non attribuisce vincite retroattive.
Nei controlli successivi per ciascuna nuova estrazione confronta due simulazioni UNIFORM e HYBRID calcolate usando esclusivamente i dati reali precedenti.
Per vedere gli esiti aprire GitHub Actions e il relativo workflow. Gli Artifacts del run contengono il report JSON.
Se una fonte è indisponibile il workflow fallisce senza alterare lo stato; il controllo successivo riprova.
Il 95,66% precedente descrive somiglianza statistica, non accuratezza predittiva.

**Test locale:** PYTHONPATH=TWIN90 python -m unittest discover -s TWIN90 -p test_twin90_live.py -v
