# V210 — Analisi dell'APK originale ricevuto dall'utente

Data 28 ottobre 2026. Analisi locale dell'archivio `MyLotteries.zip` contenente `MyLotteries.apk`.

**Provenienza verificata:** APK 67.704.092 byte, SHA-256 `857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a`. Identico alla versione studiata in V190. Nel pacchetto sono presenti 234 file JS. Analizzato integralmente `assets/www/main.79046245.js`.

## Chiamante di `scrollToElementsNotification` trovato

- Offset 657782: `mounted()` del componente 10eLotto valuta `this.$route.query.hasOwnProperty("scroll")` e richiama `this.scrollToElementsNotification(this.$route.query.scroll)`.
- Offset 658163: il watcher `"$route.query"` richiama lo stesso metodo quando viene inserito il parametro `scroll`.
- Offset 660408: se il valore equivale a `"10elotto"`, dopo 1000 ms viene invocato `scrollTo(".estrazione_diecielotto")`.
- Offset 660570: `scrollTo` usa `this.$root.$refs.newAppContainer.scrollTo({top:t.offsetTop-30,behavior:"smooth"})` e poi elimina la query dal router.

**Risposta alla domanda V208:** il trigger immediato è la query interna del router; non abbiamo identificato un bottone o URL pubblico che la imposti. Una ricerca sull'intero JavaScript non ha trovato un link statico `?scroll=10elotto`.

## Seconda strada documentata: hash della Home

- Offset 740880: la route Home è `/home`.
- Offset 641497: la Home assegna ID ai componenti da `o.name`, salvo quelli esclusi.
- Offset 694459: le sole esclusioni ID sono `bannerTop` e `inEvidence`.
- Offset 1062141: la configurazione predefinita prevede `{name:"estrazione10elotto",componentName:"estrazione10elotto",position:4,visible:true}`.
- Offset 700564: `deferScrollToHash()` legge `this.$route.hash`, cerca il DOM con `document.getElementById` e scorre `newAppContainer` fino a quell'elemento; ritenta se il contenuto non è ancora pronto.
- Offset 701679: watcher `$route` richiama `deferScrollToHash()` quando la Home riceve un hash.

**Ipotesi da verificare sul normale Android virtuale:** la route interna `/home` con ancora `#estrazione10elotto` potrebbe portare in vista la card, se il componente è presente nel layout corrente. Non è un link esterno testato, né una prova di accesso alla diretta.

## Sicurezza e limiti

Nessuna richiesta verso un endpoint protetto, nessuna modifica dell'APK. Nessuna sequenza originale dei 20 numeri recuperata. Non modificati `main`, `sniper.py`, Superambo3, V114/V121 o HARD LOCK. Tutto resta sul ramo `diagnostica/v186-app-route`.
