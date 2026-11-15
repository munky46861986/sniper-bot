# SUPERAMBO3 — PAIR80_SOURCE H2 SHADOW

Aggiornamento: 15 novembre 2026.

## Regole

- Le nove decine sono 01–10, 11–20, ..., 81–90.
- Per ciascuna decina scatta un segnale solo se nella stessa decina escono almeno cinque numeri a t−2, meno di cinque a t−1 e almeno cinque a t.
- La selezione dell'ambo usa gli ultimi **80 concorsi consecutivi della medesima giornata**, compreso il concorso t. Conteggia le co-presenze di tutte le 45 coppie della decina e sceglie la coppia più frequente. Per le parità vince la coppia con numeri più piccoli.
- Dopo la segnalazione si osserva H1, quindi H2 solo se H1 è perdente. Nessuna puntata reale; saldo virtuale €1/colpo e incasso **ipotetico** €14 per ambo.
- Mancanza di concorsi o cambio di giornata => segnali pendenti interrotti, non classificati come perdita, e reset del warmup. Nessun segnale retroattivo durante il primo caricamento dell'archivio.
- I metodi legacy restano **completamente presenti nel codice e nei vecchi file di stato**, ma non vengono aggiornati in questa modalità.

## Modalità

- Il nuovo \`sniper.py\` lancia di default \`SUPERAMBO3_MODE=PAIR80_ONLY\`.
- Per riavviare il vecchio motore ABC: \`SUPERAMBO3_MODE=LEGACY_ABC\`. Non usare entrambi i bot contemporaneamente con lo stesso token Telegram.
- \`pair80_shadow.py\`: logica e sottostato indipendente \`pair80_shadow\` dentro \`distance_abc_state.json\`.
- \`pair80_runtime.py\`: polling, warmup da fonti esistenti, persistenza, Telegram e rotazione runner.
- \`test_pair80_shadow.py\`: test sintetici non connessi a Telegram. Lancio: \`python test_pair80_shadow.py\`.

## Comandi Telegram

\`/pair80\` — Stato totale

\`/pair80oggi\` — Stato della giornata

\`/pair80segnali\` — Segnali recenti

\`/pausestato\` — Lista metodi in pausa

## Sicurezza del deploy

Le modifiche sono su un **branch separato**. Non cambiano il bot \`main\` finché non verranno esaminate e integrate. Le righe di cron del vecchio workflow rimangono invariate.

Per validare prima di un merge: eseguire i test, verificare token/chat nella configurazione esistente, assicurarsi che la fonte restituisca 80 estrazioni contigue, e osservare alcuni giorni di segnali SHADOW. Non integrare come strategia con denaro reale sulla base dei backtest esistenti: non hanno dimostrato un rendimento positivo.

## Esito replay storico (eseguito fuori da GitHub, su archivio libreria)

- 2025: 812 segnali chiusi a H2, 91 vincenti.
- 2026 fino al 18 ottobre: 762 segnali chiusi a H2, 90 vincenti.

I segnali interrotti da buchi a fine giornata/non contiguità vengono conservati separatamente e non conteggiati come H2 chiusi.
