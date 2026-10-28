# Sisal 10eLotto — prova di accesso browser GitHub (28 ottobre 2026)

## Risultato verificato
Workflow GitHub [40690310043](https://github.com/munky46861986/sniper-bot/actions/runs/40690310043), commit `1e53fc76e9dd0ff9c13e31a42149b9bac27a45a0`, concluso **success** per lo script diagnostico, ma **nessuna estrazione acquisita**.

Playwright Chromium normale sul runner Ubuntu, URL pubblico `https://www.sisal.it/10elotto`. Nel log:
```
{"url":"https://www.sisal.it/10elotto","accessible":false,"draw_visible":false,
 "error":"Error: Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR ..."}
```
Non è una prova di 403 né del comportamento di un browser sul PC dell'utente; è una mancata connessione del runner. Non fare bypass di accesso o browser stealth, né dichiarare che la cattura server 24/7 funzioni.

## Risultati già acquisiti localmente (separati da GitHub)
- Video PC Sisal del 28/10/2026: estrazione n. 102, 20 numeri nell'ordine visibile `3,66,24,25,23,64,72,17,8,89,12,57,85,45,44,33,36,43,62,41`, confermata manualmente sul frame finale.
- Riconoscitore colore/geometria offline: 20 palline su `final_0435.jpg`, 0 su fotogrammi incompleti precedenti.
- Prova integrata con browser locale su pagina HTML simulata: 20 centri individuati, 20 valori letti da elementi HTML, test CSV `added -> duplicate` riuscito.
- Estensione Chrome locale (DOM pubblico) testata sulla medesima pagina simulata: evento `CAPTURE` con ordine dei 20 numeri corretto.
- Nessuna delle due automazioni è stata ancora verificata sulla pagina Sisal live dopo la prova PC dell'utente. Non inventare risultati.

## Limite persistente
GitHub Actions `schedule` funziona solo dal branch predefinito ed è best-effort: non è una soluzione garantita per tutti i concorsi a cinque minuti, soprattutto mantenendo `main` intatto. Rif. https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule.

## Requisiti invariati
No costi; nessuna giocata; nessun account; nessuna modifica al branch `main`, Superambo3, V114, V121, HARD LOCK o GOLD MASTER.
