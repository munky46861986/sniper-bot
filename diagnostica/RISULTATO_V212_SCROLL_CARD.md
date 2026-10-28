# V212 — Diagnosi confermata del contenitore Home e delle schede

**28 ottobre 2026**. Run completati: [40682843610](https://github.com/munky46861986/sniper-bot/actions/runs/40682843610) e [40683043854](https://github.com/munky46861986/sniper-bot/actions/runs/40683043854).

APK ufficiale verificato con SHA-256 `857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a`. Sono stati ispezionati staticamente **345 file JS/CSS**, senza eseguirli e senza richiedere endpoint protetti.

## Scoperte grounded
1. Il template Vue della Home costruisce `<div ref="newAppContainer" class="new-app-container has-tab-bar">` con `scroll-behavior: smooth` (bundle `main.79046245.js`, offset circa **554081**).
2. Il componente 10eLotto ha il parametro iniziale `collapsed:true` nella configurazione predefinita (bundle `main.79046245.js`, offset circa **1063341**).
3. La Home usa `homeCardsOpened`, salvato in localStorage: `toggleCardCollapse(e,t)` aggiorna la scheda aperta; `isCollapsed(e)` confronta la scheda richiesta con la scheda attiva (offset circa **700000**).
4. Il component 10eLotto legge `this.homeComponent.isCollapsed(this.name)` (offset circa **658503**).
5. `deferScrollToHash` e `scrollToElementsNotification` si riferiscono a percorsi **interni al router Vue**, non a URL Android pubblicamente verificati.
6. Nel dump Android V211 il pulsante `Segui l'estrazione` è presente ma `bounds=[0,0][0,0]`; la WebView non segnala `scrollable=true`.
7. Tuttavia il test V211 con focus da tastiera ha prodotto uno screenshot effettivamente più basso nella Home dopo **otto TAB**, mostrando «10eLotto Giocate pronte»; quattro `DPAD_DOWN` hanno continuato lo scorrimento. È la prima navigazione visibile che supera i precedenti swipe/Page Down falliti.

## Conseguenza operativa
Provare a usare il focus Android standard per portare **visivamente** sullo schermo la scheda estrazione10elotto e il suo normale controllo `Segui l'estrazione`; premere solo quando visibile, non forzare click di nodi invisibili né modificare l'APK. La V213 applica esattamente questa diagnosi.

**Non ancora acquisito:** ordine originale dei 20 numeri; nessun archivio continuativo 24/7. Non alterati `main`, Superambo3, V114, V121, HARD LOCK.
