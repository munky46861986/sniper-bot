# V191 — Risultato su server GitHub

Data: 28 ottobre 2026. GitHub Actions: https://github.com/munky46861986/sniper-bot/actions/runs/40649931612

## Test

È stata effettuata **una sola richiesta POST**, senza credenziali, al servizio `raccolteFrequentiV2.json` citato nel codice pubblico My Lotteries. Parametri: `dataEstrazione=2026-10-27`, `numeroRaccolte=1`, `progressivoGiornaliero=226`. Era il concorso già registrato nel video per il confronto.

## Esito

**HTTP 403 — accesso negato.** Nessuna risposta JSON utile e nessuna sequenza recuperata. Il test si è fermato senza retry e senza aggirare il blocco. Il job GitHub è verde solo perché il programma ha gestito correttamente il caso 403: verde non significa recupero riuscito.

Questo non dimostra che il servizio non abbia i numeri, né che la data sia nel formato atteso. Dimostra soltanto che la richiesta non autenticata del server GitHub non è stata autorizzata.

## Conclusioni combinate V190–V191

- `assets/www/748.d52aa2da.js`, `init()`: l'animazione riempie `numberToExtract` iterando `giocata.numeri` e verificando l'appartenenza a `numeriDaEstrarre`.
- `estrazioneVentina()` usa `numberToExtract.shift()`: l'animazione conserva l'ordine della lista così costruita.
- L'array `giocata.numeri` ha un legame tecnico diretto con l'ordine animato; non equivale però a un ordine fisico del sorteggio certificato.
- L'endpoint non è al momento accessibile con la richiesta GitHub standard; **l'acquisizione automatica a PC spento non è realizzata**.
- Non inviare credenziali, token né aggirare 403. Cercare una fonte documentata e autorizzata o usare la raccolta visiva validata.

Bot principale `main`, `sniper.py`, V114, V121 e HARD LOCK non modificati.
