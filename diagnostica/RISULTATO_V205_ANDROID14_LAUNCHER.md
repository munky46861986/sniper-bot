# V205 — Diagnostica Android 14: errore dell'emulatore

28 ottobre 2026, run originale V205 https://github.com/munky46861986/sniper-bot/actions/runs/40662334405 e nuova prova V205b https://github.com/munky46861986/sniper-bot/actions/runs/40662824639.

## Evidenze
- V205 ha riconosciuto e installato l'APK, ma non ha superato il popup `Allow My Lotteries to send you notifications?`; il testo della UI era `Don’t allow` con apostrofo tipografico diverso dal codice iniziale. Screenshot e XML salvati nel primo artifact.
- V205b ha corretto l'apostrofo, ma l'emulatore ha presentato un **dialogo di sistema diverso**: `Pixel Launcher isn't responding`, pulsanti `Close app` e `Wait`; il codice, progettato per le notifiche, non ha fatto ulteriori click. Questa è evidenza di instabilità del launcher nell'emulatore Android 14, **non prova di errore My Lotteries**.
- Nessuno dei due run ha raggiunto la Home o la diretta. Lo stato GitHub `success` si riferisce solo alla diagnostica completata.

## Sviluppo successivo
V206 esegue gli stessi gesti su Android 12 (API31), senza richiesta Android 13+ di notifiche, per isolare problemi delle versioni di sistema. Non sono stati forzati endpoint o protezioni.

Tutto sul ramo diagnostico; bot principale e HARD LOCK invariati.
