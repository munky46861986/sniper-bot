# V197 — Sblocco riuscito della schermata privacy e schermata introduttiva

Data: 28 ottobre 2026. Run GitHub: https://github.com/munky46861986/sniper-bot/actions/runs/40655780128

## Esito provato dall'UI Android

APK ufficiale verificato, installato in emulatore Android 11; package `it.lottomatica.lotto`. Senza cliccare `Accetta`, è stato selezionato **`Continua senza accettare`**, individuato dal resource ID `it.lottomatica.lotto:id/close_banner_text`, coordinate `[162,243][300,260]`, click al centro `(231,251)`.

- Prima: attività `com.onetrust.cordova.CMPActivity`.
- 3 secondi dopo: attività **`it.lottomatica.lotto/.MainActivity`**. Nessun banner privacy.
- 15 secondi dopo: UI principale visibile sotto il tutorial **Fai3 Fai4** `Grande novità: Estrazione ogni 5 minuti`, che espone il bottone **`Fine`** `[211,456][240,471]`.
- Nel dump della schermata sotto il tutorial: scheda **`10eLotto`**, stato di estrazione in corso e pulsante **`Segui l'estrazione`** (quest'ultimo inizialmente fuori viewport; bounds `[0,0][0,0]`).
- Log Chromium di app contengono messaggi `COUNTDOWN-FREQUENTE-CONTROLLER: _getTimeCountDown response` e richieste di risultati `estrazioneFai`; si vede `navigator.onLine true`. Questa è prova di attività dell'app, non dell'ordine di estrazione.

**Sottolineatura:** l'animazione in ordine originale non è ancora stata raggiunta o verificata. Non confondere risultati già disponibili con la sequenza in comparsa. Il precedente problema privacy V195/V196 era probabilmente transitorio (il tocco di V197 è stato eseguito sui bounds rilevati, con pausa), ma la causa precisa del primo insuccesso non è dimostrata.

## Azione successiva

V198 naviga con normali click UI: `Fine`, `10eLotto`, eventuale `Segui l'estrazione`. Non usa acquisti, autenticazione, chiamate 403, accessi privati, e non modifica bot.

## Isolamento e costo

Solo ramo `diagnostica/v186-app-route`; invariati main e Superambo3, V114, V121, HARD LOCK. Runner standard di GitHub repository pubblico. Non è Android persistente 24/7.

Artifact GitHub V197: `V197-privacy-diagnostic`.
