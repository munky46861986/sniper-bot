# V200 — Navigazione Home Android My Lotteries: limite verificato

Test GitHub: https://github.com/munky46861986/sniper-bot/actions/runs/40657676110 (28 ottobre 2026).

## Esito
- Android virtuale gratuito e APK ufficiale installati e avviati con successo.
- Pulsante `Continua senza accettare` premuto; `CMPActivity` lascia posto a `MainActivity` (conferma della diagnosi V197).
- Schermata introduttiva Fai3 Fai4 chiusa con click `Fine` a coordinate documentate; Home visibile.
- L'estrazione e il pulsante `Segui l'estrazione` erano presenti nei dati dell'app Home in V197, ma fuori area visibile con `bounds=[0,0][0,0]`.
- V200 ha effettuato otto scroll normali della Home. Gli screenshot sono sostanzialmente fermi sulla parte superiore (banner, loghi giochi e promo); il dump WebView è intermittente/inizialmente vuoto, poi vede le stesse 24 voci in alto. `Segui l'estrazione` non è diventato cliccabile nel viewport.
- **Nessuna sequenza progressiva di 20 numeri acquisita**, nessun feed del sorteggio verificato. Il risultato verde GitHub indica test terminato, non acquisizione riuscita.

## Interpretazione
La navigazione iniziale su Android è fattibile senza denaro. La pagina `10eLotto` cliccando l'icona rotonda, come visto in V199, apre la **schedina di gioco** anziché i risultati. Non utilizzare `PROSEGUI` o altri comandi di giocata. La difficoltà restante consiste nel raggiungere la visualizzazione dell'estrazione in modo sicuro tramite UI, oppure una fonte autorizzata di video.

## Prove
Artifact V200-home-live nel run GitHub, screenshot `s_after_intro.png`, `s_home_scan_8.png`, XML e `report.json`.
Tutti i file solo sul ramo `diagnostica/v186-app-route`; nessuna modifica al bot principale, V114, V121, HARD LOCK.
