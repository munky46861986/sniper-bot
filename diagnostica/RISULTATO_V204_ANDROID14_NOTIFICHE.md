# V204 — Confronto Android 14 non concluso per dialogo notifiche

GitHub Actions https://github.com/munky46861986/sniper-bot/actions/runs/40661880720 (28 ottobre 2026), artifact V204-android14-ui.

## Evidenze
- APK My Lotteries installato con successo sull'emulatore Android 14 (API 34).
- La prima schermata è il prompt di sistema **Allow My Lotteries to send you notifications?**, con pulsanti **Allow** e **Don't allow**.
- Il test V204 era stato progettato per trovare subito `Continua senza accettare` (privacy OneTrust); non l'ha trovato, perché coperto dal prompt di sistema.
- V204 si è quindi fermato dopo la cattura del permesso notifiche. **Non dimostra** che Android 14 abbia risolto lo scroll della Home e non dimostra accesso alla diretta.

## Passo successivo
V205 rifiuta con il pulsante di sistema **Don't allow**, poi rifiuta cookie facoltativi e ripete la stessa ispezione Home a risoluzione grande. Nessun consenso marketing, login o accesso a pagamento.

Solo ramo `diagnostica/v186-app-route`, Superambo3 invariato.
