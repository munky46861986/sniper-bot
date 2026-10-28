# V190 — Risultato verificato sull'APK ufficiale

**Eseguito:** GitHub Actions run 40649556924, 28/10/2026. SHA-256 APK: `857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a` (identico a V175/V183). Fonte: `https://mylotteries.it/mobile/download/android/MyLotteries.apk`.

## Catena di lettura numeri (provata tramite codice)

**`assets/www/6065.a703ff3b.js`**: il controller emette `ESTRAZIONEFREQUENTE-GET-CURRENT-EXTRACTION` con `{dataEstrazione, numeroRaccolte:1, progressivoGiornaliero}`. Nella risposta `raccolteFrequenti[0]`, crea una copia `LOL_Utils.cloneJSObject(i)` in `model.currentExtration` prima di assegnare `model.listExtrations`.

**`assets/www/748.d52aa2da.js`**: `init()` fa un reset e poi:
```js
this.giocata.numeri.forEach((function(t){
  this.giocata.numeriDaEstrarre.indexOf(t)<0
     ?this.numberExtrated.push(t)
     :this.numberToExtract.push(t)
}),this)
```
Dunque **l'ordine dei numeri che devono ancora essere animati dipende dall'ordine di `giocata.numeri`, non dall'ordine di `numeriDaEstrarre`**. `estrazioneVentina()` usa `this.numberToExtract.shift()` per mostrare progressivamente i numeri.

**Due `.sort()` nello stesso componente** appartengono a computed properties `numeriSorted` e `numeriOvertimeSorted`, ciascuna usa `Array.from(...).sort()` — **copia e ordina per la presentazione**, non modifica direttamente l'array `giocata.numeri`.

**`fixDelayNumber()`**: se `numeriDaEstrarre.length` è 17–19, ne imposta il contenuto a una copia di `giocata.numeri`. Il filtro nell'`init` continua ad attraversare `giocata.numeri`.

**Il wait component del controller ordina `listExtrations[].numeri` in-place**. Perciò non utilizzare `listExtrations` come prova dell'ordine animato, e tenere presente che i due modelli possono essere distinti.

## Interpretazione e limiti

Questa è **prova statica forte** su come l'animazione riproduce l'array `giocata.numeri`. Non dimostra come il server ordini la risposta, né se la sequenza riprodotta sia l'ordine fisico del sorteggio. Il server automatico per ricevere il JSON non è ancora stato verificato; non aggirare risposte 403.

## Materiali

- [Workflow V190](https://github.com/munky46861986/sniper-bot/actions/runs/40649556924)
- Artifact `V190-risultati`, file `contesti_v190.csv` e `riepilogo_v190.json`.
- Codice di acquisizione indipendente: `diagnostica_v190_run.py` + `diagnostica_v190_offline.py`.

## Isolamento

Solo documentazione sul ramo diagnostico. `main`, `sniper.py`, `sniper.yml`, Superambo3, V114, V121 e HARD LOCK invariati.
