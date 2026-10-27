# Analisi flusso estrazione animata 10eLotto — checkpoint V189

Fonte: APK pubblico My Lotteries, SHA256 `857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a`, già esaminato nei report V183 e V187. **Studio statico, non verifica live.**

## Catena comprovata dal codice

1. Controller `assets/www/6065.a703ff3b.js`:
   - alla scadenza del countdown emette `ESTRAZIONEFREQUENTE-GET-CURRENT-EXTRACTION`;
   - payload: `{dataEstrazione,numeroRaccolte:1,progressivoGiornaliero}`;
   - ascolta l'evento `ESTRAZIONEFREQUENTE-GET-CURRENT-EXTRACTION|SERVICE-MODULE-getCurrentExtraction`;
   - riceve risposta che contiene `raccolteFrequenti[0]` e `durataEstrazioneNumeroMillisecondi`.
2. `_checkParameterCurrentExtration` richiede `numeriDaEstrarre.length > 0`, progressivo corrispondente, numeri oro inclusi nella ventina.
3. In `_responseCurrentExtraction_`: `i.delayNumber=t.durataEstrazioneNumeroMillisecondi`; copia `i` in `model.currentExtration` e cambia lo stato in `START_EXTRACTION`.
4. Componente `estrazioneFrequente-extration`: su `START_EXTRACTION` esegue `updateExtraction`, copiando `parent.model.currentExtration` in `giocata`.
5. Componente di animazione in `assets/www/748.d52aa2da.js`: `estrazioneVentina()` mostra progressivamente `this.numberToExtract.shift()`.

## Da verificare (non dedurre come accertato)

- Come `giocata.numeriDaEstrarre` diventa `numberToExtract` e se subisce riordini / shuffle.
- Se `numeriDaEstrarre` nel JSON originale coincide col video My Lotteries su uno stesso concorso.
- Indirizzo HTTP pubblico che alimenta `SERVICE-MODULE-getCurrentExtraction`. HTTP 403 va rispettato, senza aggiramenti.
- Se la risposta da server arriva già con i 20 numeri prima dell'animazione e se è disponibile a GitHub Actions senza app autenticata.
- Il fatto che il componente riproduca una sequenza non prova che corrisponda all'ordine fisico del sorteggio né che dia capacità predittiva.

## Prossima prova utile

Ispezione statica autorizzata e mirata dell'assegnazione a `numberToExtract`, quindi confronto *solo su un endpoint legittimamente accessibile* con l'ordine registrato dal video My Lotteries dello stesso concorso (201, 210, 211 o 226, 27/10/2026). Non utilizzare l'archivio ordinato per fare questa verifica.

## Isolamento

Questo file è solo documentazione sul ramo `diagnostica/v186-app-route`. Non modificare `main`, `sniper.py`, `.github/workflows/sniper.yml`, i parametri V114/V121 o HARD LOCK.
