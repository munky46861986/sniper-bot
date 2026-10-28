# V211 — Collegamento Android registrato /estrazioni

Data 28 ottobre 2026. Run GitHub: https://github.com/munky46861986/sniper-bot/actions/runs/40669908290

## APK verificato

MyLotteries.apk 67.704.092 byte; SHA-256 `857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a`. AndroidManifest.xml e resources.arsc registrano `https://mylotteries.it/estrazioni` come VIEW/BROWSABLE per la MainActivity.

## Test di navigazione effettivo

Android 12 virtuale su GitHub Actions: APK installato, privacy rifiutata mediante «Continua senza accettare», app Home visibile. Invocato Android ACTION_VIEW con l'URL registrato e package `it.lottomatica.lotto`. Android risponde `Status: ok` e `intent has been delivered to currently running top-most instance`; Activity `it.lottomatica.lotto/.MainActivity`.

**Risultato:** non compare la diretta 10eLotto. Screenshot 7 e 27 secondi dopo il link sono identici; stessa Home iniziale. In immagine 320×640 si osservano solo 26 piccole differenze di valori colore nella porzione 0,130–320,570 fra prima e dopo. Nessuna ventina in ordine di comparsa.

## Separazione importante

`scrollToElementsNotification("10elotto")` è attivato internamente da `$route.query.scroll`; il link registrato `/estrazioni` è differente e non si è dimostrato capace di aprire il riquadro 10eLotto. Evitare di ripetere lo stesso test o affermare che ci sia un feed funzionante.

## Sicurezza

Nessun login, giocata, bypass 403 o modifica a `main`, `sniper.py`, Superambo3, V114, V121 o HARD LOCK. Solo ramo `diagnostica/v186-app-route`.