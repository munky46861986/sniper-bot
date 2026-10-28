# V207 — Risultato del test di un ciclo completo 10eLotto su Android gratuito

**Eseguito**: 28 ottobre 2026, [workflow GitHub Actions 40664467979](https://github.com/munky46861986/sniper-bot/actions/runs/40664467979). Artifact `V207-ciclo-estrazione` (id 12805168810).

## Condizioni del test

- APK ufficiale My Lotteries verificato, installato con successo su emulatore Android 12 (API 31).
- Accesso standard senza autorizzare consensi facoltativi. Schermata Home aperta a risoluzione 600×1180.
- 16 screenshot `cycle_00.png` … `cycle_15.png` presi dal **2026-10-28 09:31:42.891 UTC** al **2026-10-28 09:37:57.628 UTC** = circa **375 secondi (6 minuti e 15 secondi)**.
- Nessuna operazione di gioco, autenticazione, aggiramento di blocchi né chiamata diretta a endpoint.

## Esiti oggettivi

1. **Sedici frame completi, nove hash diversi** se si considera l'intera schermata.
2. Analisi pixel per pixel dei frame (600×1180), escludendo il banner e la barra Android:
   - regione `(0,205,600,1105)` = **un solo hash di contenuto** su tutti i 16 frame; **zero pixel diversi** tra campioni consecutivi;
   - regione di Home `(0,225,600,700)` = un solo hash;
   - navigazione inferiore `(0,1105,600,1180)` = un solo hash.
   - Solo `(0,0,600,205)` cambiava: barra superiore/orologio (e area promo sovrastante), senza rappresentare una sequenza numerica.
3. In `cycle_06.xml` (09:34:12 UTC) l'albero accessibilità contiene:
   - `Estrazione in corso`;
   - `Estrazione n° 54 del 28/10`;
   - `Segui l'estrazione` (elemento cliccabile ma `bounds=[0,0][0,0]`);
   - `Estrazione tra00:44` (`bounds=[0,0][0,0]`).
   La presenza di queste stringhe mostra che il componente esiste nell'albero, **non** che il pulsante sia visibile sul display o che il video sia già in funzione.
4. Altri dump XML nel ciclo sono incompleti/vuoti, quindi non possiamo ricostruire con sicurezza l'evoluzione dell'intero countdown dalla sola accessibilità. Gli screenshot sono completi.
5. `opened_live=false`: **non è stata aperta la diretta**, **non è stata letta la sequenza di comparsa dei 20 numeri**.

## Conclusione

Un ciclo di osservazione di oltre cinque minuti, senza interventi manuali, **non è sufficiente** a far comparire l'animazione nella porzione di Home visibile. L'ipotesi che bastasse attendere la scadenza del conto alla rovescia non è stata confermata. Il problema è raggiungere la porzione / schermata dell'app che ospita il componente di estrazione.

### Prossima direzione diagnostica

Evitare altri test identici di scroll/timer. Studiare la gerarchia della Home nell'APK e il contenitore che rende visibile il riquadro `estra_header` / `estrazione_diecielotto_scrollTo` oppure testare la normale navigazione accessibile verso quel riquadro (focus/scroll-to-visible), senza forzare servizi o avviare giocate.

**Isolamento**: solo ramo `diagnostica/v186-app-route`; `main`, `sniper.py`, V114/V121, HARD LOCK e i workflow principali non modificati.
