# Superambo3 — PAIR80 LIVE SHADOW: SINGOLO + DOPPIO

Aggiornamento: 15 novembre 2026.

## Attivazione

Il workflow GitHub Actions `.github/workflows/sniper.yml` esegue
`python pair80_dual_runtime.py`, che importa le funzioni originali
di `sniper.py` **senza modificare quel file**.

SINGOLO e DOPPIO sono entrambi attivi per nuovi concorsi in **LIVE SHADOW**
e inviano su Telegram i segnali e gli esiti H1/H2. NON effettuano
acquisti, giocate, pagamenti o puntate reali.

Il workflow originale viene cambiato soltanto nella riga `run:`.
Tutti gli altri moduli, i metodi storici e i file JSON di stato restano
nel repository, ma non vengono eseguiti da questo nuovo entrypoint.

## Regola — PAIR80 SINGOLO

- Per ogni decina standard 01–10, 11–20, ..., 81–90:
  quando nel concorso appena concluso escono **almeno cinque**
  numeri della decina, il metodo SINGOLO può generare un segnale.
- Si seleziona l'ambo della **stessa decina** con più co-presenze
  nelle ultime **80 estrazioni consecutive della stessa giornata**,
  compresa quella che genera il segnale.
- In caso di parità si sceglie la coppia numericamente minore.
- H1 e H2: chiusura alla prima uscita dell'ambo; altrimenti STOP H2.

## Regola — PAIR80 DOPPIO

- Per la medesima decina, servono almeno cinque numeri a t-2,
  **meno di cinque** a t-1 e di nuovo almeno cinque a t.
- La scelta dell'ambo è identica a SINGOLO con finestra W80.
- Anche DOPPIO verifica H1 e H2 separatamente.

**Attenzione:** ogni segnale DOPPIO è contemporaneamente anche un
segnale SINGOLO. Il bot registra e notifica *entrambi*, senza sommare
le due osservazioni come se fossero eventi indipendenti.

## Warmup e sicurezza dei dati

- Servono 80 concorsi consecutivi **nella stessa giornata estrattiva**.
- Il warmup iniziale recupera la storia senza inviare segnali retroattivi.
- Salti nel feed o cambio giornata interrompono i pendenti, senza
  conteggiarli come perdite, e resettano la finestra a zero.
- Il nuovo stato è sotto la chiave `pair80_dual_shadow` del file
  `distance_abc_state.json`; nessun reset dei contatori storici ABC.
- Il bot persiste su GitHub tramite la logica di salvataggio esistente.
- Incasso virtuale impostato a **14 € ipotetici**, puntata virtuale 1 €
  per colpo: **non** si tratta di una quota reale verificata.

## Comandi Telegram

- `/pair80`: entrambi i metodi, totale
- `/pair80oggi`: entrambi i metodi, giornata corrente
- `/pair80singolo`: solo SINGOLO
- `/pair80doppio`: solo DOPPIO
- `/pair80segnali`: segnali più recenti
- `/pausestato`: elenco metodi in pausa

## Verifica

Eseguire:
```bash
python -m unittest -v test_pair80_dual
python -m py_compile pair80_dual.py pair80_dual_runtime.py sniper.py
```

Replay 2025–2026 già verificato prima del rilascio con archivi 2025
(77.565 concorsi) e 2026 fino al 18/10 (82.568 concorsi).
Il 2026 presenta 762 segnalazioni DOPPIO con H2 osservabile,
90 successi; 21.266 SINGOLO con H2 osservabile, 1.983 successi.
Alcuni H1 vincenti vicino a fine giornata sono conteggiati nel
monitor live pur non essendo nel precedente backtest che richiedeva
la disponibilità di H2.

**I dati passati non dimostrano una strategia redditizia.**
