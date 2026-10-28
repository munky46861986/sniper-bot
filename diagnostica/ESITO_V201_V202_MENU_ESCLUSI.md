# V201–V202 — Stato navigazione My Lotteries

Data: 28 ottobre 2026.

## V201 — [test GitHub](https://github.com/munky46861986/sniper-bot/actions/runs/40658792925)
L'APK originale si apre su Android 11 GitHub e il normale rifiuto della privacy funziona. Il menu inferiore **News&info** si apre; è dedicato a **News & Info**, FAQ e assistenza conto gioco, non alla diretta 10eLotto. Swipe e PAGE_DOWN non rendono visibile il pulsante `Segui l'estrazione`; la Home V200 resta pixel-per-pixel ferma dopo otto swipe (salvo barra di stato). Nel dump UI Android il pulsante `Segui l'estrazione` ha antenati `[0,0][0,0]`, quindi è dentro contenuti non visibili; non dedurre che sia semplicemente oltre il bordo inferiore.

## V202 — [test GitHub](https://github.com/munky46861986/sniper-bot/actions/runs/40659538992)
Il menu inferiore **Verifica vincite** apre una richiesta permesso per la **fotocamera**, utilizzata per inquadrare il codice di una giocata. Non è il percorso dei risultati e non è stata autorizzata alcuna acquisizione video o utilizzato il conto gioco. L'interfaccia mostra `Inquadra il codice`, `Digita il seriale`. Non è adatta all'obiettivo.

## Risultato
Due menu esclusi con prove concrete. La strada da seguire è l'analisi statica del componente `estrazione5minuti` e del relativo percorso di apertura, non altre pressioni sugli stessi tab. **Nessuna sequenza originale è stata ancora acquisita**.

Solo ramo diagnostico; main, Superambo3, V114, V121, HARD LOCK invariati. Nessun acquisto, nessuna elusione di 403.
