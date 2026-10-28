# V211 — app link pubblico: risultato verificato

Data: 28 ottobre 2026. Ramo esclusivo `diagnostica/v186-app-route`.

## Run eseguito
- Run riuscito: https://github.com/munky46861986/sniper-bot/actions/runs/40669908290
- Commit: `bd564e75acfb921797c7a7ead07060c0f9fd2a5f`
- Job: `122753755556`
- Artifact disponibile al controllo: `V211-android-link`, id `12807463782` (scadenza 31/10/2026).
- APK installato: `Performing Streamed Install / Success`.
- Rifiuto facoltativo privacy riuscito: `Continua senza accettare`, tap [231,251].
- Tutorial: `Fine` non trovato nel dump, usato tap di fallback precedentemente verificato [225,463].
- Android Intent standard `ACTION_VIEW` per `https://mylotteries.it/estrazioni`, package `it.lottomatica.lotto`: exit 0, `Status: ok`, `Activity: it.lottomatica.lotto/.MainActivity`.
- Android segnala `Activity not started, intent has been delivered to currently running top-most instance`: app riceve l'intent nell'activity già esistente, non prova che abbia navigato.
- Screenshot `home_before_link`: 188053 byte; `after_link_7s`: 188019 byte; `after_link_27s`: 188019 byte. Le sole dimensioni non provano identità delle immagini né ingresso in diretta. UI text degli screenshot: liste vuote, quindi non conclusivo.
- **Nessuna sequenza dei 20 numeri catturata o verificata.** Nessuna prova che si sia aperta la diretta.

## Correzione e nuovo test
Il vecchio run 40669512604 falliva per SyntaxError; lo script sul ramo era già corretto al controllo successivo. Aggiunto allo stesso workflow lo step `python -m py_compile diagnostica_v211_android_link.py`, commit `5101c014b4a1d6aae1437aff2685d37cc5fde042`.
Il run https://github.com/munky46861986/sniper-bot/actions/runs/40680861207 era in corso all'ultimo controllo di questo rapporto; lo step di sintassi e il download dell'APK risultavano riusciti. Non anticipare il suo esito.

## Decisione diagnostica
Non ripetere alla cieca il link: `/estrazioni` è registrato nel manifest ma l'Intent potrebbe lasciare la Home invariata. Confrontare screenshot effettivi e UI prima/dopo. Se immutati, cercare solo normali gesti/controlli visibili per il componente 10eLotto. `/home#estrazione10elotto` e `?scroll=10elotto` sono indizi del router **interno**, non app link pubblici dimostrati.

Mai modificato `main`, `sniper.py`, Superambo3, V114, V121 o HARD LOCK. Nessuna spesa e nessun tentativo di superare HTTP 403.
