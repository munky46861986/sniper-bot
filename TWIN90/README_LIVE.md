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

## Simulazioni preventive registrate (aggiornamento)

- Alla lettura di un concorso reale valido, TWIN90 prepara **solo** il concorso immediatamente successivo, quando mancano almeno 30 secondi all'orario atteso.
- Invia le 20 Base simulate, Oro, Doppio Oro e 15 Extra per HYBRID e UNIFORM come **simulazioni preventive**, mai come risultati reali o numeri consigliati per giocare.
- Segna `sent_at` soltanto quando Telegram conferma l'invio prima del concorso, conservando la previsione originale nello stato sul ramo `twin90-live-state`.
- All'arrivo dell'estrazione successiva confronta **esclusivamente** quella simulazione già inviata e memorizzata. Se non è stata consegnata in tempo, invia il risultato reale con l'avvertenza `Nessuna simulazione preventiva verificata` e non incrementa `advance_stats`.
- Le precedenti statistiche retrospettive restano separate; `advance_stats` parte da zero e misura solo confronti preventivi certificati dall'invio.
- La frequenza di controllo è circa 5 minuti e dipende dalla disponibilità delle fonti e del runner GitHub. Non ogni concorso avrà necessariamente una simulazione preventiva.
