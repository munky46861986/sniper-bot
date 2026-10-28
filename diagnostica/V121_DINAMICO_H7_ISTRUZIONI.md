# V121 DINAMICO — CORRETTO: ricalcolo a ogni estrazione, controllo da H7/H8

## File unico completo
`sniper_V121_DINAMICO_H7_COMPLETO.py` — copia **completa** dell'intero bot, con modifiche limitate alla classe `V121LiveShadow` e alla fusione della relativa memoria V121 `_merge_v121_state`. `sniper.py` del ramo principale non è stato toccato.

## Come funziona davvero
- A ogni estrazione t, il vecchio modello congelato V121 del 2025 genera una nuova previsione di 20 numeri usando lo storico disponibile fino a t. Questa previsione riguarda t+1, **non è bloccata**.
- Quando arriva t+1, il bot confronta i risultati con quella previsione H1 e aggiorna i soliti punteggi V121 e V114.
- Il nuovo monitor conta H1, H2, H3, ... come numero di **verifiche H1 consecutive**, non come durata di una singola ventina fissa.
- Dai controlli **H7 in poi** (oppure H8 impostando `V121_ZONE_START_H=8`) registra i numeri corretti della previsione di QUEL concorso, separati in fascia numerica bassa `01-30`, media `31-60`, alta `61-90`; conserva anche le posizioni nella lista crescente (primi 7 / 7 centrali / ultimi 6).
- Finché H1 totalizza meno di 7 numeri, continua a H8, H9, H10 ... **sempre usando una previsione nuova per ogni draw**.
- Al primo H1 con >=7 **dopo il gate**, manda il dettaglio delle zone e chiude il ciclo; al concorso successivo riparte da H1.
- Gli H1 da >=7 **prima** di H7/H8 restano nei vecchi contatori V121 e V114, ma non chiudono il nuovo monitor, che parte soltanto al gate richiesto.
- Le classifiche degli esiti osservati aggiornano automaticamente frequenze per fascia, posizione e singolo numero; normalizzano per il numero di candidati e applicano un piccolo smussamento. **Non cambiano il modello V121**, non provano una capacità predittiva e non avviano giocate.
- Se una previsione H1 manca o è saltata una estrazione, il ciclo viene interrotto e il conteggio H riparte da capo: non si inventa la continuità.

## Impostazione predefinita e persistenza
Impostazione predefinita: `V121_ZONE_START_H=7`. Per la variante richiesta, impostare `V121_ZONE_START_H=8`. La soglia 7/20 resta fissa in entrambi i casi. Il bot salva il nuovo monitor **dentro la stessa chiave V121** già utilizzata nello state operativo, mantenendo i contatori H1 precedenti; al primo avvio inizia un nuovo conteggio H1 senza ricostruire in modo fittizio il passato.

## Sicurezza / test
`test_v121_dynamic_h7.py`: test sintetici senza rete di H7 fino a successo a H9, H8 configurabile, confronto dinamico fra previsioni H1 successive, attribuzione numeri e fasce, rilevazione degli intervalli mancanti e salvataggio della memoria.

Workflow isolato: `.github/workflows/test-v121-dynamic-h7.yml` sul ramo `diagnostica/v186-app-route`. Produce anche il file ZIP contenente il codice completo, per essere scaricato.

**Non è stato installato sul bot attivo**: il ramo `main`, l'originale `sniper.py`, Superambo3, V114, HARD LOCK e GOLD MASTER non sono stati modificati. `V121_MODELLO_NONLINEARE_2025.txt` rimane indispensabile e invariato.

