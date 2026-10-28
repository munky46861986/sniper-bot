# Ricerca delle fonti per l'ordine di comparsa dei 20 numeri — 28 ottobre 2026

Obiettivo: lista cronologica `n01..n20` del 10eLotto ogni 5 minuti **nell'ordine mostrato in diretta**; un elenco crescente non soddisfa il requisito. Non è richiesto né necessario alcun conto gioco.

## Risultato di ricerca e verifica
**Nessuna fonte pubblica/documentata del 2026 è stata identificata e verificata come fornitrice dell'ordine completo n01..n20** accessibile a un server esterno e utilizzabile gratuitamente 24/7.

### Pista storica concretamente documentata
Un archivio del forum Chilkat conserva una richiesta del 2013 a `https://vetrina.giocodellotto.it/serviziFE/10elotto/raccoltaFrequente.json` con `POST` e parametri anno/mese/giorno/progressivoGiornaliero. Mostra la risposta HTTP 200 ricevuta **nel 2013** con il campo `numeri` nell'ordine non crescente:
```text
12 88 41 30 37 74 46 13 42 60 56 80 35 20 51 07 85 76 24 26
```
Fonte: https://www.chilkatforum.com/questions/3303/vb6-problem-json-website

**Test pubblico attuale limitato:** un accesso GET senza autenticazione allo stesso percorso il 28 ottobre 2026 ha restituito HTTP **405 Method Not Allowed**. Questo non prova che il servizio POST sia ancora operativo, pubblico o consentito; non abbiamo testato richieste POST o riutilizzato sessioni/cookie. Anche la risposta 2013 **non dimostra** che l'array fosse nell'ordine dell'animazione; la verifica richiederebbe un confronto concorso-per-concorso con un video pubblico.

### Fonti ufficiali correnti
- https://mylotteries.it/10elotto-estrazioni-e-archivio.html : conferma la diretta nell'app My Lotteries e l'archivio; nessun feed numerico cronologico pubblicamente documentato.
- https://www.lotto-italia.it/10-e-lotto/estratti.html : storico fino a 12 mesi, con risultati, Oro e Extra. Dall'interfaccia pubblica non è confermato alcun campo n01..n20.
- https://www.sisal.it/10elotto/ultima-estrazione : risultati e concorsi passati; nessun servizio documentato per la successione originale.
- https://mylotteries.it/ : supporto ufficiale My Lotteries: `info@mylotteries.it`, numero verde `800 929394` (7–20).

### Fonte terza con API realmente documentata
https://lottologia.com/10elotto5minuti/sistemi-personali espone al browser strumenti read-only `GetLastDraw`, `GetDrawByDate`, `GetDraws` per numeri delle estrazioni; la pagina archivio visualizza i risultati in ordine crescente. **Non è provato** che l'API conservi l'ordine di apparizione e non può essere usata come sostituto verificato.

### Evidenza del nostro progetto
Il video Sisal inviato dall'utente il 28/10/2026 registra l'estrazione **102** in quest'ordine:
```text
03 66 24 25 23 64 72 17 08 89 12 57 85 45 44 33 36 43 62 41
```
Tale sequenza è un riferimento di confronto per qualsiasi eventuale futura API. Una seconda sequenza completa del concorso 112 è leggibile da uno screenshot finale ma non è stata acquisita automaticamente.

## Prossimo test decisivo
Chiedere al gestore ufficiale:
1. se è conservato l'ordine n01..n20 della **modalità ogni cinque minuti**, distinto dalla lista crescente;
2. se l'ordine mostrato dal player è pari all'ordine di estrazione oppure è rimescolato per sola presentazione;
3. se esistono dati di prova o endpoint **documentati e autorizzati** per la sola lettura, eventualmente riutilizzabili su un server remoto;
4. quali condizioni o costi si applichino, e se è disponibile l'archivio storico.

Contatto ufficiale documentato: https://mylotteries.it/ — info@mylotteries.it.

## Vincoli
Nessun aggiramento 403/anti-bot, nessuna richiesta a endpoint protetti, nessuna sessione utente e nessuna spesa. Nessuna modifica a `main`, Superambo3, V114/V121, HARD LOCK, sniper.py o GOLD MASTER. La possibilità di funzionamento continuo gratuito a PC spento **non è stata dimostrata**.
