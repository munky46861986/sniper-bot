# SUPERAMBO FUSION V1 / EVOLUTIVO × HYBRID — SOLO SHADOW

Versione congelata: `SUPERAMBO_FUSION_V1_SHADOW_FROZEN`.

**Non piazza giocate, non accede a credenziali di puntata, non altera strategie preesistenti.**
Due esperimenti separati avviati esclusivamente da un segnale preventivo
`RITARDATARI_EVOLUTIVO_V1_FROZEN` passato ai filtri e in coda Telegram.

1. `EVOLUTIVO_DECINE_DNA`: i 20 numeri di RITARDATARI EVOLUTIVO
   intersecati con i 20 del modello specialist DECINE. Se DNA MASTER
   ha un candidato nel gruppo condiviso, quel candidato ha precedenza;
   poi si ordinano gli altri numeri in modo crescente.
2. `EVOLUTIVO_TWIN90_HYBRID`: i 20 numeri di RITARDATARI EVOLUTIVO
   intersecati con i 20 BASE previsti dal TWIN90 HYBRID.

Si prende **una coppia per esperimento**, solo se almeno due numeri
coincidono. Se un incrocio non produce due numeri, la sua coppia
non viene pubblicata né valutata. Non è richiesta concordanza obbligatoria
con DNA MASTER: i suoi segnali LIVE sono molto rari.

Il controllo indipendente di ciascun esperimento usa i due numeri più
piccoli della previsione `SPECIALIST CONTROLLO`, già generata prima del
concorso. È una regola deterministica e fissata prima dei nuovi risultati.

Il metodo scrive `superambo_fusion` nello stato persistente sul ramo
`twin90-live-state`. La previsione viene allegata al medesimo messaggio
preventivo Telegram di TWIN90 e confermata solo a seguito di risposta
positiva API Telegram. Nessuna verifica viene conteggiata se manca
preannuncio tempestivo o se si salta un concorso; i contatori non vengono
azzerati da restart.

Per ciascuna coppia sono registrati **successi nello stesso concorso**
H1, H2, H3, H4 e H5, e separatamente `within5`, cioè almeno un ambo
in una qualsiasi delle cinque estrazioni. `within5` non equivale
a cinque vittorie e la presenza di numeri in estrazioni diverse non
costituisce un ambo.

## Controllo preliminare (esplorativo, NON validazione)

Sui 32 vecchi segnali EVOLUTIVO con sequenza H1–H5 ricostruibile:
- RITARDATARI ∩ DECINE, prima coppia crescente: 31 segnali eleggibili;
  H1=2, H2=1, H3=1, H4=0, H5=1, almeno un ambo entro H5: 4/31.
- RITARDATARI ∩ TWIN90 HYBRID, prima coppia crescente:
  31 segnali eleggibili; H1=4, H2=2, H3=1, H4=2, H5=3,
  almeno un ambo entro H5: 12/31. Controllo 10/31.
- Le percentuali sono estremamente instabili, i segnali si sovrappongono
  temporalmente e la regola è stata controllata retrospettivamente.
  I nuovi contatori prospettici devono restare separati da questi dati.

Il tasso teorico per un ambo prefissato in una estrazione uniforme di 20
numeri su 90 è `(20/90)*(19/89) ≈ 4.744%`. Cinque estrazioni
indipendenti producono `1-(1-p)^5 ≈ 21.6%` di almeno una comparsa,
ma richiederebbero cinque puntate per giocare ogni colpo.
Nessun vantaggio o profitto è dimostrato. NESSUNA PUNTATA REALE.

Test: `python -m unittest discover -s TWIN90 -p 'test_twin90_fusion.py' -v`
