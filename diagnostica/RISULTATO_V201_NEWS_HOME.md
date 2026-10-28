# V201 — Menu News & Info e navigazione Home

Fonte: GitHub Actions V201 https://github.com/munky46861986/sniper-bot/actions/runs/40658792925 (28 ottobre 2026). Artifact V201-news-nav (screenshots, XML UI e report.json).

## Evidenze dalle schermate acquisite
- L'APK My Lotteries si installa in Android 11 gratuito. Con `Continua senza accettare` si supera la privacy e il tutorial `Fine` si chiude.
- Il bottone in basso **News&info** apre realmente la pagina `News & Info`, contenente promozioni, assistenza e FAQ. Nessuna diretta 10eLotto visibile.
- Il bottone in basso **Home** riporta effettivamente alla Home (prova: `home_return.png`). Alcuni dump accessibilità (per esempio `home_return.xml`) erano **stale**, riportavano ancora testo News&Info dopo il cambio pagina: meglio affidarsi agli screenshot per la pagina corrente.
- In `news_after_scroll.png` non emerge una pagina nuova: identica alla News iniziale.
- Il comando pagina giù e swipe Home non mostrano `Segui l'estrazione`.
- Il pulsante diretta `Segui l'estrazione` era stato visto in precedenti dati UI ma con bounds `[0,0][0,0]` (nascosto, non direttamente cliccabile).

## Limiti
Questo non prova che la diretta non esista: solo che News&info non la espone e la Home scorre male a risoluzione 320×640. Nessun numero in ordine animato è stato acquisito.

## Prossima verifica
V202 misura la Home a 320×1180 e 600×1180 tramite normale configurazione `adb shell wm size`, analizzando screenshot e accessibilità prima di concludere che l'elemento è raggiungibile. Nessun bypass o login, nessuna giocata.

Solo ramo `diagnostica/v186-app-route`, nessuna modifica a Superambo3, V114, V121, HARD LOCK.
