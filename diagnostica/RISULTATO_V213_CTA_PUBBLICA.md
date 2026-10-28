# V213 — Pulsante pubblico 10eLotto individuato; destinazione UI confermata staticamente

Data: 28 ottobre 2026. **Solo ramo diagnostico**, nessun intervento sui bot attivi.

## Evidenza visiva verificata
[Workflow V213](https://github.com/munky46861986/sniper-bot/actions/runs/40683274668) concluso con successo. Artifact `V213-focus-navigation` id `12814167234`.
Dopo 10 comandi Android standard `KEYCODE_TAB=61`, screenshot `tabs_10.png` 320×640:
- Scheda rossa Fai3/Fai4 fra circa y=413 e 498: pulsante «Segui l'estrazione» relativo al Fai3/Fai4.
- Scheda blu **10eLotto** fra circa y=510 e 596, etichetta «Estrazione n° 94 del 28/10» e pulsante «Segui l'estrazione» intorno a x=60–177, y=568–589.
- Il dump `tabs_10.xml` è vuoto, quindi il test cercava nella fonte sbagliata; `visible_live_button=false` non prova l'assenza del pulsante.

## Il comando del pulsante blu, direttamente dal codice dell'APK originale
Il bundle `assets/www/main.79046245.js` contiene, in due varianti del template 10eLotto presso gli offset ~652586 e ~655610:

```javascript
on:{click:function(t){
  e.homeComponent.open("estrazione5minuti"),
  e.tracking("diretta")
}}
```

Il pulsante Fai3/Fai4 vicino, in un template diverso, esegue invece `open("estrazioniFai")`: sono due percorsi UI distinti.

Nella Home, il metodo `open(e)` inoltra `OPENSECTION` alla normale gestione dei percorsi dell'app. La rotta `estrazione5minuti` è pertanto **la destinazione interna documentata del normale pulsante pubblico 10eLotto**. Questo non dimostra automaticamente che sia raggiungibile da un URL esterno o quale sarà l'aspetto della schermata dopo l'apertura.

## Stato
La V213 non ha cliccato il pulsante 10eLotto, non ha aperto la diretta e non ha catturato una sequenza originale. Il tentativo successivo di creare un automatismo V214 è stato bloccato dai controlli della connessione GitHub; i file V214 sono risultati inesistenti. Non aggirare il blocco.

Per ulteriore diagnosi non interattiva è stata avviata una nuova esecuzione del workflow statico V212 per tracciare la destinazione `estrazione5minuti`. Nessuna autenticazione, acquisto, richiesta a un servizio protetto o spesa.

**Non modificati** `main`, `sniper.py`, Superambo3, V114, V121, HARD LOCK o GOLD MASTER.

## Verifica aggiuntiva: gestione della rotta nel codice (V212c)
Il [run statico 40685121409](https://github.com/munky46861986/sniper-bot/actions/runs/40685121409) è **completato con successo**, e ha prodotto l'artifact `V212-home-scroll-static` id `12814821118`, comprendente `cta_route_traces.json` e `cta_route_traces.md`. L'APK analizzato è lo stesso con SHA verificato.

Sono stati confermati i passaggi ordinari nel bundle `assets/www/main.79046245.js`:

```text
pulsante blu 10eLotto «Segui l'estrazione»
 -> e.homeComponent.open("estrazione5minuti")  (~652522 o ~655548)
 -> this.$ActionsService.execAction(Rt.kl.OPENSECTION,{target:e}) (~699688)
 -> this.$BUS.$emit("OPEN-DEEP-LINK", t.target, t.query) (~568506)
```

La stessa sezione contiene anche un pulsante alternativo `Guarda la diretta Live Show` che, in specifiche condizioni di streaming, invoca `toggleCollapse()` (non `estrazione5minuti`). Non confondere le due azioni.

**Conseguenza:** è stata trovata la catena applicativa interna associata al pulsante pubblico, ma **non** un URL pubblico verificato. Non è stata aperta la diretta e non è stato raccolto alcun ordine originale di venti numeri. Il passo interattivo rimane non effettuato: l'automatismo V214 è stato bloccato dai controlli del collegamento GitHub.
