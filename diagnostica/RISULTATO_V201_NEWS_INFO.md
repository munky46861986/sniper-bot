# V201 — Navigazione alternativa nell'app My Lotteries

**GitHub Actions:** https://github.com/munky46861986/sniper-bot/actions/runs/40658792925 (28 ottobre 2026).

## Evidenze verificabili
- All'avvio dell'app ufficiale in emulatore Android, il rifiuto dei cookie facoltativi e il comando `Fine` permettono di aprire la Home.
- `Segui l'estrazione` compare nel dump XML V200 sotto antenati `[0,0][0,0]`. Non è un pulsante realmente visibile; non è provato che sia soltanto più in basso nella Home.
- Gli screenshot degli 8 scroll V200 sono pixel-per-pixel identici, a parte la barra di stato. Lo swipe non ha spostato il contenuto.
- In V201 il menu inferiore `News&info` si apre normalmente. Il titolo visibile è **News & Info** e l'area contiene soprattutto supporto, FAQ e assistenza al conto gioco, non la diretta 10eLotto.
- Lo scorrimento verticale in News&info non cambia lo screenshot, e il tasto PAGE_DOWN non rivela la diretta.
- **Nessuna sequenza di 20 numeri acquisita.**

## Prossimo test
V202 esamina il tab `Verifica vincite` (solo navigazione, nessuna giocata/scansione). Se non mostra risultati pubblici, evitare tentativi identici: tornare all'individuazione del componente e alla navigazione tramite funzioni documentate.

## Progetto isolato
Solo branch `diagnostica/v186-app-route`, nessuna modifica a main, Superambo3, V114, V121, HARD LOCK.
