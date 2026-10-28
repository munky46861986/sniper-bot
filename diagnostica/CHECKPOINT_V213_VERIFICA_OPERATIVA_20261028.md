# Verifica V213 — stato utilizzabile dopo il blocco V214
Data: 28 ottobre 2026. Repo `munky46861986/sniper-bot`, solo branch `diagnostica/v186-app-route`.

## Risultati effettivi
- [V213 GitHub Actions run 40683274668](https://github.com/munky46861986/sniper-bot/actions/runs/40683274668): **success**, ma `button_clicked=false` e `sequence_verified=false`. Il risultato success indica il successo dell'esecuzione, non il raggiungimento del dato.
- Artifact `V213-focus-navigation`, id `12814167234`, screenshot `tabs_10.png`: 320×640. Dopo **10 TAB** da Home il componente è visibile:
  - scheda rossa Fai3/Fai4, all'incirca y 413–497;
  - scheda blu 10eLotto, all'incirca y 510–596, «Estrazione n° 94 del 28/10» e «Segui l'estrazione» attorno a x 20–215, y 568–590. **Coordinate specifiche di quello screenshot**, non assumere che siano stabili in un altro run.
- Il dump XML di `tabs_10` non presenta testi utilizzabili; non è prova di invisibilità. La V213 ha cercato il testo XML, perciò non ha cliccato la scheda visibile.
- Nell'APK verificato, il CTA blu è collegato all'azione interna `homeComponent.open("estrazione5minuti")`, poi `OPENSECTION` e `OPEN-DEEP-LINK`. Non è stato provato un link Android esterno diretto per quella destinazione.

## Fonte ufficiale indipendente
- https://mylotteries.it/10elotto-estrazioni-e-archivio.html : la documentazione ufficiale spiega di espandere il primo box 10eLotto della Home e usare il pulsante della diretta.
- https://www.lotto-italia.it/10-e-lotto/10elotto-live-show : il Live Show descritto è un programma trasmesso fra marzo e giugno 2024, non un flusso documentato di tutte le estrazioni 2026.

## Blocco operativo e limiti da non nascondere
Il tentativo di creare la V214 interattiva su GitHub è stato **bloccato dai controlli di sicurezza**. Controllo successivo: né `diagnostica_v214_visible_live.py` né `.github/workflows/v214-visible-live.yml` risultano creati. Non riproporre la medesima operazione con altri nomi, canali o procedure per aggirare il blocco.
Nessun dato nell'ordine di visualizzazione ancora acquisito. Non dichiarare ottenuta l'animazione.
L'eventuale raccolta continuativa 24/7 non è garantibile con lo scheduler di GitHub Actions: i workflow schedulati possono tardare o saltare; il limite minimo è una esecuzione ogni cinque minuti, i runner sono temporanei. Rif. https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
Le prove su `diagnostica/v186-app-route` non vanno unite automaticamente al branch principale.

## Priorità prossima verifica autorizzata
Verificare l'apertura della **normale schermata visibile** «Segui l'estrazione» del riquadro blu, evitando il Fai3/Fai4 rosso e qualsiasi comando di acquisto. Solo dopo apertura confermata, osservare l'animazione e confrontare un concorso con uno stesso video identificato. Non assumere che l'ordine dell'animazione coincida con quello del sorteggio fisico.

## Integrità
Non alterati `main`, Superambo3, `sniper.py`, V114, V121, HARD LOCK né il bot GOLD MASTER. Nessuna spesa, nessun bypass di HTTP 403.
