# V203 — Swipe Home dai bordi su Android 11

GitHub Actions https://github.com/munky46861986/sniper-bot/actions/runs/40661201806 (28 ottobre 2026), artifact V203-edge-scroll.

## Test eseguito
Installazione APK originale My Lotteries verificato; privacy rifiutata, introduzione chiusa; Home a 600×1180 con tre swipe naturali:
- bordo destro: (589,965) → (589,155)
- bordo sinistro: (12,930) → (12,120)
- zona centrale: (300,855) → (300,130)

## Risultato
- `Segui l'estrazione` rimane nascosto, nessun click sulla diretta effettuato.
- Le immagini dopo i gesti a bordo sinistro e zona centrale sono **identiche a livello di hash SHA-256**; nessun movimento di scroll visibile.
- Il primo screenshot subito dopo il bordo destro differisce di pochi pixel rispetto ai successivi, ma non dimostra uno scroll del contenuto; la Home è nello stesso punto.
- La Home contiene anche un riquadro esterno con errore JS (osservato in V202); non è provato che tale errore impedisca lo scroll.

## Interpretazione
Il metodo dei gesti sul bordo non risolve su Android 11, e la diretta non è stata aperta. Il passo diagnostico V204 confronta una versione Android 14 usando lo stesso programma. Non aggira HTTP 403, non esegue acquisti né altera il bot.

## Isolamento
Tutto solo su `diagnostica/v186-app-route`; `main`, V114, V121 e HARD LOCK invariati.
