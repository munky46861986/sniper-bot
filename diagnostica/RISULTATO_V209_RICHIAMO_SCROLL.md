# V209 - Analisi richiamo interno della Home My Lotteries

Data 28 ottobre 2026. Studio dei contesti statici V187 e dei report V183-V208; non modifica l'app o i servizi.

## Verificato
- `assets/www/main.79046245.js` contiene `scrollToElementsNotification(e)`.
- Con `e === "10elotto"` invoca `scrollTo(".estrazione_diecielotto")` dopo 1000 ms.
- `scrollTo` usa `this.$root.$refs.newAppContainer.scrollTo({top:t.offsetTop-30,behavior:"smooth"})` e cancella i parametri di query del router.
- `toggleCollapse()` espande/riduce la card, ma non spiega come raggiungerla nella Home.
- Le finestre di V187 attestano la definizione della funzione **non la chiamata/registrazione dell'evento**.

## Limite e passo necessario
Il report V187 salva 58 contesti parziali: il tratto necessario per identificare chi richiama l'evento non è disponibile. Il programma di analisi statica V208 è stato salvato ma non eseguito perché il workflow non è stato creato. In questo ambiente il recupero diretto dell'APK originale non è riuscito. Serve una copia completa dell'APK, per esempio il file originale da 67.704.092 byte eventualmente racchiuso in ZIP, per verificare il chiamante su dati reali.

Non è stato recuperato l'ordine originale dei numeri, né creato un sistema 24/7.

## Isolamento
Repository main, sniper.py, Superambo3, V114, V121, HARD LOCK invariati. Solo checkpoint diagnostico.
