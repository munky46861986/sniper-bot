# LOTTO TWIN90 v1 — Motore statistico del 10eLotto ogni 5 minuti

**Algoritmo sperimentale eseguibile** di simulazione e analisi. Riproduce i vincoli ufficiali e una serie di statistiche storiche. **Non contiene il generatore riservato del concessionario, non replica gli stessi numeri futuri e non dimostra alcun vantaggio per giocare.** Il 95,657% indicato nel rapporto è la somiglianza media di *13 statistiche aggregate*, non la precisione predittiva.

## Che cosa fa il motore

1. Legge e controlla gli archivi 2025 e 2026: data, concorso, ventina Base, Oro1, Oro2, Extra.
2. Per ogni estrazione verifica 20 Base distinti su 90, due Oro distinti presenti nei Base e 15 Extra distinti fra gli altri 70.
3. Se un record Extra è assente o contraddittorio, lo esclude **solo** dalla calibrazione Extra, conservando i Base/Oro validi.
4. Studia per ogni numero 1–90 frequenze, ritardi, frequenze W20/W80/W288, Oro1, Oro2, Extra; analizza le nove decine ordinate `90–09,10–19,...,80–89`.
5. Costruisce una matrice 90×90 di possibili relazioni tra numeri di due estrazioni consecutive e profili delle sei fasce temporali della giornata.
6. Confronta 16 ipotesi **prima** del test 2026: casuale, frequenti, ritardatari, anti-frequenti, dipendenze, decine, Oro/Extra precedenti e modello ibrido.
7. Seleziona un modello sul periodo di validazione 2025 e lo misura sul 2026 senza riadattarlo al risultato. Se non emerge un miglioramento minimo, conserva il modello casuale.
8. Ricalibra su entrambi gli archivi un modello per simulare nuove estrazioni. Il modello completo è in `twin90_model_2025_2026.json`; il modello usato per il test indipendente è in `twin90_model.json`.
9. Genera intere giornate sintetiche in formato CSV. **Sono estrazioni inventate dal simulatore, non i risultati ufficiali e non previsioni.**

## File principali

- `lotto_twin90.py` — codice completo del motore (solo Python + numpy).
- `profilo_storico.py` — analisi storica 90 numeri e 9 decine.
- `test_twin90.py` — cinque test automatici.
- `twin90_model.json` — parametri 2025, valutati su 2026.
- `twin90_model_2025_2026.json` — parametri riaddestrati sui 160.133 concorsi.
- `twin90_evaluation.json` — confronto fuori campione e somiglianza delle distribuzioni.
- `statistiche_90_numeri.csv` — ritardi e frequenze, compresi Oro e Extra, per anno.
- `statistiche_9_decine.csv` — distribuzione delle nove decine per anno.
- `estrazioni_sintetiche_288.csv` — giornata completa simulata, modello selezionato.
- `estrazioni_288_HYBRID.csv` — giornata simulata con il modello adattivo sperimentale, senza vantaggio validato.
- `twin90_synthetic.csv` — 12.000 concorsi sintetici usati nella comparazione statistica.
- `data/2025.csv`, `data/2026.csv` — archivi originali per riprodurre il test (nel pacchetto ZIP completo).

## Come eseguirlo

Richiede Python 3.10+ e numpy:

```bash
python -m pip install -r requirements.txt
python -m unittest -v test_twin90
```

Per simulare i 288 concorsi di una giornata:

```bash
python lotto_twin90.py simulate --model twin90_model_2025_2026.json --count 288 --start 2026-11-18 --seed 42 --output giornata_sintetica.csv
```

Per provare **il modello adattivo di ricerca**, anziché quello selezionato dai test:

```bash
python lotto_twin90.py simulate --model twin90_model_2025_2026.json --mode HYBRID --count 288 --start 2026-11-18 --seed 42 --output giornata_ibrida_sintetica.csv
```

Per verificare il modello su 2025/2026 e ricalibrare tutto da zero:

```bash
python lotto_twin90.py train --archive-2025 data/2025.csv --archive-2026 data/2026.csv --model test_modello.json --report test_valutazione.json --simulations test_simulazioni.csv --sample-size 12000
python lotto_twin90.py refit --model test_modello.json --archive-2025 data/2025.csv --archive-2026 data/2026.csv --output modello_due_anni.json
python profilo_storico.py --archive-2025 data/2025.csv --archive-2026 data/2026.csv --output .
```

Per chiedere se il modello ha una classifica per il concorso successivo:

```bash
python lotto_twin90.py predict --model twin90_model_2025_2026.json --history data/2026.csv
```

**Con il modello selezionato (`UNIFORM`) non viene inventata alcuna classifica**: il test non ha identificato un vantaggio nelle probabilità dei 90 numeri.

## Interpretazione del numero 95,657%

Il simulatore è stato confrontato con 12.000 estrazioni reali del 2026 su tredici indicatori fissati nel codice: media e dispersione delle frequenze Base, sovrapposizione tra concorsi successivi, pari, somma dei numeri, decine piene, dispersione Oro1/Oro2, frequenza degli Extra.

La media dei punteggi di somiglianza relativi è 95,657%. **Tre indicatori sono 100% per costruzione** perché dipendono dai vincoli del gioco. Eliminando quei tre, la media delle dieci misure rimanenti è circa 94,35%. Questa è una metrica descrittiva *nostra*, non una certificazione di equivalenza con il generatore reale.

Allineando i 12.000 concorsi sintetici con 12.000 reali, in media coincidono **4,426 numeri Base su 20**, risultato compatibile con estrazioni indipendenti. Quindi non è stato ricostruito il generatore originario né ottenuta una precisione del 95% sui numeri.

## Sorgenti normative e limiti

- https://www.lotto-italia.it/10-e-lotto/regolamenti
- https://www.lotto-italia.it/10-e-lotto/come-si-gioca/opzioni/doppio-oro
- https://www.lotto-italia.it/10-e-lotto/come-si-gioca/opzioni/extra

Gli storici 2025 sono dal **1° gennaio al 28 settembre**; quelli 2026 dal **1° gennaio al 18 ottobre**. Non sono due anni completi. Le sei anomalie Extra sono elencate nel report e non devono essere interpolate o trattate come prova di una falla dell'estrazione. Il modello va utilizzato per ricerca e simulazione, non per assumere guadagni o convertire automaticamente le simulazioni in puntate.

## Esecuzione su GitHub Actions

La versione pubblicata nel repository `sniper-bot` risiede nella cartella `TWIN90/`.
Il workflow `.github/workflows/twin90.yml` si avvia una volta con il primo push dei file e può essere
riavviato manualmente dalla scheda **Actions → TWIN90 - laboratorio 10eLotto → Run workflow**.
Il job esegue cinque test, poi genera 288 estrazioni sintetiche `UNIFORM` e 288 `HYBRID`.
I due CSV vengono allegati come **artifact twin90-simulazioni** alla singola esecuzione GitHub Actions.
Non usa BOT_TOKEN, non manda messaggi Telegram e non lancia `sniper.py`.

I file `data/2025.csv` e `data/2026.csv` citati sopra sono presenti nel pacchetto completo scaricabile
nella conversazione originale, ma non vengono copiati nel repository: il job usa direttamente
il modello già addestrato `twin90_model_2025_2026.json`.
I comandi di addestramento richiedono di fornire gli archivi in un percorso locale.
