# V121 NONLINEARE — Posizioni e numeri bassi/medi/alti entro 9 estrazioni (28 ottobre 2026)

**Test GitHub completato:** [run 40724164836](https://github.com/munky46861986/sniper-bot/actions/runs/40724164836). Artifact `V121-position-study` id `12830694324` con `summary.json`, `cases.csv` e `report.md`. Script: `diagnostica_v121_position_backtest.py`. Esclusivamente ramo diagnostico.

## Dati e metodo
- Modello V121 LightGBM congelato nel 2025, utilizzato con la funzione `v121_predict` originale di `sniper.py`, senza modificarla.
- Storico read-only del repository: 900 estrazioni tra 2026-10-24#144 e 2026-10-27#250.
- Ricostruite **570 finestre valide** con passato disponibile e 9 future estrazioni consecutive; escluse 34 per assenza di continuità.
- Lista di 20 numeri prevista al tempo t e mantenuta **fissa** per tutte le 9 future estrazioni, senza usare dati futuri nella previsione.
- Le 570 finestre **non sono** i 1.398 test LIVE H1 già comunicati dal bot: i dati LIVE storici V121 sono conservati solo come aggregati, non previsione/esito per concorso.
- Per ogni fascia si riporta il numero di presenze diviso (candidati previsti × 9 estrazioni), così gruppi di lunghezza differente sono comparabili.

## Per posizione nella lista V121 (ordine crescente)
| Gruppo | Hit per candidato al primo colpo (H1) | Hit per candidato per estrazione nei 9 colpi | Numero previsto comparso almeno una volta in 9 |
|---|---:|---:|---:|
| **Primi 7** | 21,80% | **22,39%** | 90,00% |
| **7 centrali** | 22,21% | 22,15% | 88,92% |
| **Ultimi 6** | **23,19%** | 21,67% | 89,39% |

## Per fascia numerica
| Gruppo | Hit H1 per candidato | Hit per candidato per estrazione nei 9 | Comparso almeno una volta nei 9 |
|---|---:|---:|---:|
| **01–30** | 22,50% | **22,51%** | 90,05% |
| **31–60** | 21,74% | 22,13% | 89,22% |
| **61–90** | **23,39%** | 21,50% | 89,09% |

## Relazione con 7+
- 67/570 previsioni V121 hanno preso **7 o più numeri al primo concorso H1** (11,75%, media una ogni 8,51 nel campione).
- Nei 67 concorsi H1 da 7+, i tassi di successo individuale per fascia di posizione sono: primi 7 **35,82%** (168/469), centrali **39,23%** (184/469), ultimi 6 **37,81%** (152/402). Dato condizionato sul 7+ osservato; **non** regola predittiva.
- In **370/570 (64,91%)** finestre, la stessa ventina ottiene almeno un concorso da 7+ entro i nove futuri. In **200/570 (35,09%)** non si osserva alcun 7+ entro i 9 concorsi.

## Robustezza (per giorno di origine; frequenza per candidato per estrazione nei 9)
| Giorno | Finestre | Primi 7 | 7 centrali | Ultimi 6 | Bassi 1–30 | Medi 31–60 | Alti 61–90 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-10-25 | 94 | 24,77% | 22,80% | 22,38% | 24,48% | 23,40% | 21,67% |
| 2026-10-26 | 276 | 21,64% | **21,94%** | 21,77% | 21,70% | 21,87% | 21,72% |
| 2026-10-27 | 200 | 22,31% | 22,13% | 21,20% | 22,58% | 21,90% | 21,14% |

## Interpretazione corretta
Nei nove concorsi si osserva un lieve vantaggio dei numeri **bassi/primi 7**, ma le differenze sono piccole e **il gruppo migliore cambia da un giorno all'altro**. Il riferimento matematico per una singola previsione di un numero è 20/90 = 22,22% per concorso: tutti questi tassi sono vicini al caso. La probabilità che un numero qualunque compaia almeno una volta in nove estrazioni indipendenti è già elevata (1 − (70/90)^9, circa 89,6%). Le finestre da 9 si sovrappongono, dunque non trattarle come 570 esperimenti indipendenti. Nessuna legge verificata per giocare o alzare una puntata.

**Non modificati** `main`, Superambo3, V114, V121, HARD LOCK, `sniper.py` o il modello. Nessuna giocata automatica.
