# V202 — Esito test dimensioni display Android

Data: 28 ottobre 2026. GitHub Actions: https://github.com/munky46861986/sniper-bot/actions/runs/40660479511. Artifact `V202-screen-layout`.

## Metodo
APK MyLotteries ufficiale SHA256 già verificato; emulatore Android standard, accesso UI normale. Da Home acquisiti 3 layout: 320×640, 320×1180 e 600×1180 pixel. Nel layout 320×1180 eseguito un gesto swipe sul contenuto.

## Risultati verificati
- Cambio altezza e larghezza con `adb shell wm size`: riuscito, screenshot realmente più grandi e porzione più ampia della Home.
- A 320×1180 sono visibili `10eLotto Giocate pronte`, widget promozionali e un riquadro esterno con testo **"Application error: a client-side exception has occurred while loading ..."**. Non è dimostrato che tale errore sia la causa del mancato scorrimento.
- In entrambi i layout più grandi `Segui l'estrazione` e `Estrazione in corso` esistono nel dump XML ma hanno `bounds=[0,0][0,0]`, dunque **non sono pulsanti visibili**.
- Lo swipe da x170 y940 a x170 y210 del layout alto non modifica lo screenshot. Potrebbe aver intercettato il gesto il contenuto integrato, ma è solo un'ipotesi.
- Nessuna diretta video né sequenza numerica acquisita.

## Prossima diagnosi
V203: gesti su bordi esterni e zona di sfondo a 600×1180, evitando per quanto possibile riquadri promozionali; confronto screenshot e XML.

Nessuna spesa; nessuna modifica al bot main o HARD LOCK.
