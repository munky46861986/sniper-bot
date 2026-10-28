# V192 — Verifica della pagina pubblica Lotto Italia

Data test: 28 ottobre 2026, Actions run https://github.com/munky46861986/sniper-bot/actions/runs/40650281495

## Metodo
Browser Chromium/Playwright su GitHub, una navigazione senza credenziali a `https://www.lotto-italia.it/10-e-lotto` con due screenshot distanziati di 65 secondi. Acquisiti solo metadati delle richieste primo dominio e possibili array JSON (nessuno). Nessuna autenticazione, nessun retry del blocco, nessun aggiramento.

## Esito effettivo
- Job GitHub **success**, perché la diagnostica ha funzionato tecnicamente.
- Il browser è stato aperto correttamente.
- La pagina effettivamente vista ha titolo **Radware Block Page**, percorso `/`, in **entrambe** le catture.
- Testo identico tra le due catture; **una** richiesta del dominio ufficiale osservata.
- **0** sequenze candidate, **0** confronti con video.
- Quindi la pagina ufficiale non è accessibile dal runner GitHub in questa prova, nonostante possa essere pubblicamente consultabile da altri dispositivi.

## Stato complessivo
- V190: il componente mobile mostra i numeri secondo l'ordine attraversato in `giocata.numeri`; l'array `numeriDaEstrarre` filtra l'insieme dei numeri da animare.
- V191: la richiesta standard all'endpoint `raccolteFrequentiV2.json` restituisce HTTP 403.
- V192: la pagina pubblica Lotto Italia sul runner presenta Radware Block Page.
- Nessun feed live autorizzato che fornisca l'ordine è stato trovato.
- Non ripetere forzando blocchi. Prossima strada: chiedere accesso/documentazione al fornitore o testare acquisizione visuale solo mediante accessi e infrastrutture consentiti, nel rispetto delle condizioni del servizio.

Tutti i file di analisi sono sul ramo `diagnostica/v186-app-route`. Non modificati `main`, `sniper.py`, `sniper.yml`, V114, V121 e HARD LOCK.
