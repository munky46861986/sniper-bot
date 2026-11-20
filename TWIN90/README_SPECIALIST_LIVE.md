# TWIN90 SPECIALIST LAB V1 — LIVE (solo simulazione)

**Attivo dentro TWIN90 LIVE**, sul bot Telegram Superambo3 gia configurato. Non si deve creare un nuovo bot o aggiungere variabili Render. Utilizza le credenziali `BOT_TOKEN` e `CHAT_ID` gia presenti nei GitHub Secrets, senza leggerle o mostrarle.

## Quattro selezioni Base indipendenti

- **RITARDATARI**: considera soltanto la distanza in estrazioni dall'ultima uscita di ciascun numero. Pesa maggiormente le assenze lunghe.
- **FREQUENTI**: considera soltanto le frequenze Base negli ultimi 10, 30, 60 e 100 concorsi reali.
- **DECINE**: considera soltanto quante uscite hanno avuto le nove decine (1–10 ... 81–90) negli ultimi 60 concorsi; all'interno della stessa decina tutti i numeri hanno peso identico.
- **CONTROLLO**: 20 numeri casuali tra 1 e 90, senza pesi adattati ai risultati.

Tutti selezionano 20 Base distinti. Nessuna selezione Oro, Extra o scommessa. I parametri sono **fissi** per rendere attendibile il test in prospettiva.

## Telegram automatico

Quando TWIN90 prepara una simulazione valida per il prossimo concorso, aggiunge le quattro selezioni Base **allo stesso messaggio preventivo** che contiene HYBRID e UNIFORM. In questo modo non raddoppia il numero di notifiche.

Quando arriva il concorso reale, il **medesimo messaggio dei risultati TWIN90** mostra anche i quattro conteggi Base coincidenti, ma **solo se il messaggio preventivo contenente gli specialisti e stato confermato da Telegram prima del concorso**.

Se il runner, la fonte o Telegram sono in ritardo, non fabbrica una previsione dopo il risultato: salta il confronto per quel concorso. Prima del primo invio valido, i conteggi SPECIALIST LAB partono da zero.

## Risultati e stato

Nel branch `twin90-live-state`, file `twin90_live_state.json`:
- `specialist_lab.checked`: numero di concorsi confrontati con preventive veramente inviate.
- `specialist_lab.stats`: numero confronti, Base coincidenti totali, almeno 6/7/8, errore delle decine.
- `specialist_lab.forecasts`: 20 numeri e timestamp della simulazione per ogni concorso.
- `specialist_lab.recent`: ultimi 50 esiti.
- Lo stato HYBRID/UNIFORM rimane indipendente.

Attenzione: nelle estrazioni indipendenti ed eque non c'e una ragione statistica per cui ritardatari, frequenti o decine debbano prevedere meglio del caso. Le medie teoriche Base e 4,44/20 e le verifiche LIVE servono a capire se le ipotesi reggono su dati futuri.

## Verifica

`PYTHONPATH=TWIN90 python -m unittest discover -s TWIN90 -p test_twin90_specialists.py -v`

Workflow: `.github/workflows/twin90_live.yml`. Le verifiche degli algoritmi sono inoltre su `.github/workflows/twin90_preflight.yml`.

Non toccare `sniper.py`, PAIR80, Gold Master o altri metodi: SPECIALIST LAB riutilizza solo il ciclo TWIN90 esistente.
