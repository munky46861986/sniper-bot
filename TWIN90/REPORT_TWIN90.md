# RISULTATI REALI — LOTTO TWIN90 v1

**Data del test:** 17 novembre 2026  
**Obiettivo:** ricreare un generatore del 10eLotto 5 minuti il più fedele possibile e testarne separatamente la capacità predittiva.

## 1. Dati effettivamente elaborati

| Archivio | Concorsi | Intervallo | Extra anomali | 
|---|---:|---|---:|
| 2025 | 77,565 | 01/01–28/09 | 4 |
| 2026 | 82,568 | 01/01–18/10 | 2 |
| **Totale** | **160,133** | Anni incompleti | **6** |

Base e Oro di tutti i record erano validi. Quattro righe del 2025 avevano intersezioni illecite tra Base ed Extra; due righe del 2026 erano senza Extra. I sei Extra sono stati esclusi dalle stime relative a Extra, ma i loro Base e Oro sono stati conservati.

## 2. Due risultati distinti: somiglianza e previsione

**Somiglianza statistica:** **95.657%** media delle 13 misure definite nel codice, confronto fra 12.000 estrazioni sintetiche e 12.000 reali del 2026. Tre metriche sono 100% per definizione dei vincoli: eliminandole, le restanti dieci fanno **94.35%** in media. Questi punteggi non indicano che si indovini il 95% dei numeri.

**Somiglianza estrazione per estrazione:** circa **4,426 Base su 20** in comune, 12.000 confronti, anziché 19 o 20. La media teorica per due ventine casuali indipendenti è 4,444.

## 3. Addestramento senza contaminazione

- Addestramento iniziale: gennaio–giugno 2025.
- Validazione dei 16 metodi candidati: luglio–settembre 2025.
- **Test indipendente**: 82.280 estrazioni del 2026 (le prime 288 sono memoria iniziale per i segnali).
- Modello che ha vinto la validazione 2025: **UNIFORM**; modello selezionato: **UNIFORM**.
- Dopo il test, i parametri sono stati ricalibrati sull'intero archivio dei due anni per la sola simulazione del futuro, in un file separato.

| Metodo | Perdita logaritmica 2026 (più bassa meglio) | Media numeri corretti nella top-20 | Ambo top-2 H1 |
|---|---:|---:|---:|
| UNIFORM | 0.529706 | 4.445/20 | 4.808% |
| HYBRID | 0.531596 | 4.442/20 | 4.807% |
| TRANSITION | 0.529711 | 4.449/20 | 4.815% |
| HOT80 | 0.534458 | 4.446/20 | 4.737% |
| COLD80 | 0.534276 | 4.446/20 | 4.807% |

La top-20 del modello casuale non è una vera previsione: tutte le 90 probabilità sono uguali. I ~4,44 numeri corretti sono l'attesa matematica, non un vantaggio.

## 4. Che cosa è stato ricostruito con esattezza

- 20 numeri Base **tutti distinti** (1–90).
- Oro1 e Oro2 distinti, **entrambi appartenenti ai Base**.
- 15 Extra distinti, **nessuno appartenente ai Base**.
- Nove decine nel nuovo ordine **90–09, 10–19, 20–29, ... 80–89**.
- Sequenza giornaliera 288 concorsi con intervallo nominale cinque minuti.
- Stato riproducibile mediante `seed`, e modalità sperimentale ibrida con frequenze, ritardi, decine, Oro, Extra, transizioni 90×90 e fasce orarie.

## 5. Statistiche storiche leggibili

Le classifiche complete per ogni numero e ogni decina si trovano nei CSV:

- `statistiche_90_numeri.csv`: frequenze generali, Oro1, Oro2, Extra; ritardi finali Base, Oro, Extra; W20/W80/W288.
- `statistiche_9_decine.csv`: numero medio di Base, decine con ≥5 e ≥6 numeri, decine vuote.
- `profilo_storico.json`: classifiche per entrambi gli anni.

Numeri Base più frequenti nel 2025 (fino a settembre): **41, 55, 59, 8, 1, 78, 57, 33, 14, 68**.

Numeri Base più frequenti nel 2026 (fino a ottobre): **68, 27, 19, 72, 77, 26, 86, 7, 44, 63**.

La diversa classifica dimostra che la frequenza passata da sola non identifica un sistema stabile.

## 6. Anomalie documentali rilevate

- 2025-09-16, concorso 258: missing/invalid/overlap Extra.
- 2025-09-16, concorso 259: missing/invalid/overlap Extra.
- 2025-09-19, concorso 256: missing/invalid/overlap Extra.
- 2025-09-19, concorso 257: missing/invalid/overlap Extra.
- 2026-07-08, concorso 1: missing/invalid/overlap Extra.
- 2026-07-08, concorso 2: missing/invalid/overlap Extra.

Queste incongruenze potrebbero essere errori di archivio; non abbiamo elementi per chiamarle un difetto dell'estrazione ufficiale.

## 7. Esecuzione e test

Cinque test automatici superati, inclusi: validità dei 20+2+15, nove decine non sovrapposte, stessa simulazione per lo stesso seed, cambiamento al variare del seed, assenza di dati futuri nelle variabili predittive.

**Conclusione tecnica:** il generatore sintetico è plausibilmente fedele alle statistiche più importanti, ma il migliore algoritmo per la previsione dei Base sui dati indipendenti resta quello equiprobabile. **Non abbiamo scoperto il generatore reale né un vantaggio economico.**