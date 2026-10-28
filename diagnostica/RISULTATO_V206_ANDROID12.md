# V206 — Android 12: confronto con Android 11

28 ottobre 2026, test GitHub https://github.com/munky46861986/sniper-bot/actions/runs/40663369388; artifact `V206-android12-ui`.

## Esito verificato
- Android 12 (API31) installa l'APK My Lotteries originale, SHA-256 verificato; app aperta.
- `Continua senza accettare` funziona; tutorial `Fine` chiuso.
- Home resa su 320×640 poi su 600×1180.
- Tre swipe come in V203 (margine destro, sinistro, zona centrale). Screenshot `wide_before.png`, `after_right_edge.png`, `after_left_edge.png` **identici SHA256**; quello dopo il gesto centrale differisce di una piccola parte della pagina, ma non mostra l'avanzamento della Home.
- `Segui l'estrazione` non è apparso visibile; nessuna diretta aperta né sequenza originale acquisita.
- Gli XML dei due ultimi snapshot sono vuoti/incompleti (`parse_error`): **non usare** questi dati per concludere cosa è visibile; gli screenshot sono disponibili e mostrano la Home ferma.

## Conclusione
Il blocco della navigazione Home non dipende semplicemente da Android 11, poiché si ripete su Android 12. Android 14 è rimasto inconclusivo per i popup di sistema/Pixel Launcher ANR. È ingiustificato ripetere swipe identici.

I contesti statici V187 indicano che `Segui l'estrazione` / `Guarda la diretta` hanno condizioni di visibilità legate al countdown `timeSecondCountDown<=0`, allo streaming e allo stato della card. **Ipotesi da verificare**: la disponibilità del pulsante varia durante una specifica finestra di estrazione e il widget resta altrove fuori viewport. Prossimo test dovrebbe osservare un ciclo completo di estrazione attraverso UI standard, non reiterare gesti su annunci promozionali. Nessun bypass 403 o login.

## Sicurezza
Solo ramo `diagnostica/v186-app-route`. Nessuna spesa o variazione a Superambo3, V114/V121 o HARD LOCK.
