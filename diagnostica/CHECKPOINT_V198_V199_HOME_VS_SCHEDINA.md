# Checkpoint V198/V199 — UI My Lotteries dopo il consenso

Data: 28 ottobre 2026. Test: 
- [V198](https://github.com/munky46861986/sniper-bot/actions/runs/40656382173)
- [V199](https://github.com/munky46861986/sniper-bot/actions/runs/40656946621)

## Fatti verificati
- Il rifiuto dei cookie facoltativi apre `MainActivity`; avviso introduttivo `Fai3 Fai4` mostra il pulsante `Fine` in `[211,456][240,471]`.
- Nel primo V198 l'UI XML era temporaneamente vuota dopo il rifiuto, nonostante lo screenshot mostrasse `Fine`; per questo il test si è fermato. Non era blocco del servizio.
- In V199 il normale tocco sul pulsante `Fine` (coordinate confermate da screenshot precedente) ha chiuso il tutorial. La Home reale si apre con card promozionali e una fila di icone di gioco.
- Il pulsante tondo `10eLotto` nella fila di icone Home apre **la schedina**, con selezione numeri e `PROSEGUI`. Non è la diretta: **non usare** il pulsante `PROSEGUI` per il progetto.
- I dati della Home contengono una sezione `Estrazione in corso` e un pulsante `Segui l'estrazione`, inizialmente fuori vista. Quest'ultimo è il target del V200 (scroll della Home senza aprire la schedina).

## Limiti
Nessuna prova ancora della sequenza originale. L'APK mostra informazioni pubbliche, ma non è stato osservato l'array di venti numeri nel corretto ordine durante l'animazione. Non trasformare informazioni di navigazione in una dichiarazione di feed ottenuto.

Solo ramo diagnostico, nessun acquisto, nessuna modifica a Superambo3/V114/V121/HARD LOCK.
