# Checkpoint V194–V196: Android gratuito su GitHub Actions

Data: 28 ottobre 2026

## Prove effettuate (runner standard di repository pubblico)
- [V194](https://github.com/munky46861986/sniper-bot/actions/runs/40653845416): Android 11 (x86_64), download APK pubblico MyLotteries 67.704.092 bytes, SHA-256 `857d0b801541d8d42ccf51e8a5e4fa1c9124fbd871cdfcec97b2065a7e23587a`. ABI supportate APK: arm64-v8a, armeabi-v7a, x86, x86_64. `adb install`: SUCCESS, package `it.lottomatica.lotto`. `monkey` avvia app, visibile CMPActivity della privacy.
- [V195](https://github.com/munky46861986/sniper-bot/actions/runs/40654393766): tocco su **Continua senza accettare**, screenshot dopo 15–65 secondi e UI dump: CMPActivity e finestra privacy ancora visibili, nessuna vista estrazione.
- [V196](https://github.com/munky46861986/sniper-bot/actions/runs/40654951715): tocco di rifiuto cookie seguito dal normale tasto Android BACK. Resta visibile la stessa `com.onetrust.cordova.CMPActivity` e i relativi pulsanti; nessuna vista estrazione.
- L'esito verde dei workflow significa che i test hanno eseguito le diagnostiche: **non significa che la raccolta della ventina funzioni**.

## Risultato confermato
L'APK ufficiale si installa e avvia su emulatore Android gratuito GitHub. Non è stata raggiunta la schermata delle estrazioni. La UI della privacy non è stata superata nei due tentativi standard. Questo potrebbe dipendere da comportamento dell'app, incompatibilità ambiente o rete, ancora non accertato. Non è possibile concludere di avere trovato ordine originale né acquisizione automatica.

## Sicurezza
Non sono stati aggirati 403 o protezioni di rete, né accettati cookie facoltativi. Nessun token SpawnDroid utilizzato da V194/V196. È possibile revocare il segreto `SPAWNDROID_UPLOAD_KEY_V193` se non più necessario.
Solo ramo diagnostico; `main`, `sniper.py`, il bot Superambo3, V114, V121 e HARD LOCK non sono stati modificati.

## Passo successivo realistico
Prima di altri costosi avvii dell'emulatore, analizzare logcat CMP Onetrust e verificare se l'app funziona in emulatore senza blocco iniziale tramite percorsi ordinari supportati. Se fallisce, rivalutare l'accesso a sorgenti pubbliche/documentate e non dichiarare operazione 24/7. GitHub Actions fornisce macchine temporanee per test, non un Android persistente sempre acceso.
