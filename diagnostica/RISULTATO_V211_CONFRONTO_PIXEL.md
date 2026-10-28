# V211 — verifica pixel e navigazione Home, 28 ottobre 2026

## Prova eseguita
GitHub Actions run [40681299508](https://github.com/munky46861986/sniper-bot/actions/runs/40681299508), concluso `success`; artifact `V211-android-link`, id `12813745000`.

Lo ZIP dell'artifact è stato scaricato e le immagini PNG sono state effettivamente aperte e confrontate: tutte hanno formato **320×640**. Confronto con Pillow/ImageChops pixel per pixel di `home_before_link.png` contro:
- `after_link_7s.png`: nessun pixel differente.
- `after_link_27s.png`: nessun pixel differente.
- `after_page_down_1.png`: nessun pixel differente.

I file PNG presentano impronte SHA-256 diverse, ma **i pixel decodificati coincidono**. Il confronto delle sole impronte dei file, quindi, non rappresentava una prova sufficiente. Per i tre Page Down, i relativi screenshot sono uguali anche tra loro.

## Dati UI
Il dump `home_before_link.xml` include due nodi WebView (`android.webkit.WebView`) con `scrollable=false` e bounds `[0,24][320,640]`. Il pulsante `Segui l'estrazione` compare nell'albero accessibilità come cliccabile, ma ha bounds `[0,0][0,0]`, quindi **non è visibile nel viewport**. Alcuni snapshot successivi hanno XML vuoto, perciò non vanno usati come prova di assenza di componenti.

La Home visibile mostra banner, `Verifica o Scansiona`, `Accedi o Registrati`, pulsanti giochi e pubblicità, non il riquadro di estrazione. Si conferma che `https://mylotteries.it/estrazioni` raggiunge la `MainActivity` ma non ha modificato la Home visibilmente.

## Limiti
Non è stata visualizzata la diretta 10eLotto e **non è stato acquisito l'ordine originale dei 20 numeri**. Non tentare di premere nodi a bounds `[0,0][0,0]` né di attivare schedine. Non ripetere inutilmente i medesimi swipe/Page Down.

## Passaggio successivo
La diagnosi V212 esamina **staticamente** il JavaScript e CSS verificati nell'APK, con focus su `newAppContainer`, il router e le regole di scorrimento. Questa è una pista di diagnostica e non un accesso già risolto alla diretta.

Nessuna modifica al ramo `main`, Superambo3, V114, V121, HARD LOCK, né accesso a servizi protetti.
