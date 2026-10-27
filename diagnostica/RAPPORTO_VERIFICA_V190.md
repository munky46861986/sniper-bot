# V190 — Audit effettivo delle evidenze sulla sequenza 10eLotto

Data: 27 ottobre 2026. Solo analisi statica, senza modifiche al bot.

## Evidenze disponibili

- **Controller corrente:** `assets/www/6065.a703ff3b.js`, frammento V187 intorno all'offset 2899. `_checkParameterCurrentExtration` verifica che `numeriDaEstrarre.length > 0` e il `progressivoGiornaliero` corrisponda. Il controller distingue `currentExtration` da `listExtrations`.
- **Animazione:** `assets/www/748.d52aa2da.js`, contesti V183 attorno all'offset 12967. `estrazioneVentina` legge il prossimo numero con `this.numberToExtract.shift()`; nel frammento noto non avviene ordinamento in quel momento.
- **Archivio:** `archive10eLotto-index-js.a89fbbef.js` ordina gli elementi `numeri` con `.sort((e,n)=>e-n)`. L'archivio non è quindi una prova dell'ordine animato.

## Cosa manca (non va inventato)

Il frammento V183 relativo a `748.d52aa2da.js` non copre per intero il blocco di inizializzazione di `numberToExtract`. Non è dimostrato se avvenga una copia diretta di `numeriDaEstrarre`, un riordinamento, o un'altra trasformazione. **Non dichiarare confermato questo passaggio.**

Non è stato individuato un endpoint live pubblicamente accessibile e verificato che restituisca la sequenza. Un 403 non deve essere aggirato. Non è provato che l'ordine di animazione sia l'ordine fisico di sorteggio.

## Strumento aggiunto

`diagnostica_v190_offline.py` analizza un APK già disponibile localmente, legge i file esatti `748.d52aa2da.js`, `6065.a703ff3b.js` e `main.79046245.js`, estrae le assegnazioni e i contesti. Non effettua traffico di rete né giocate. È stato controllato sintatticamente e su un APK **sintetico di prova**: non è ancora stato eseguito sull'APK ufficiale.

Per verificare il passaggio mancante è necessario eseguire lo script sull'APK completo tramite un ambiente autorizzato e confrontare la sequenza restituita, sullo stesso concorso, con il video registrato da My Lotteries.

## Sicurezza del progetto

Tutto resta nel ramo `diagnostica/v186-app-route`; invariati `main`, `sniper.py`, `sniper.yml`, V114, V121 e HARD LOCK.
