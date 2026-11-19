# NEXUS AI Trading — Paper Trading

Progetto sperimentale per simulare operazioni su BTC/ETH e osservare token emergenti. **Nessun trading reale, nessuna leva e nessun wallet collegato.** Non esiste alcuna garanzia di guadagno.

## Aggiornamenti

Questo repository pubblico ospita il codice e le release ufficiali. La pipeline `Publish NEXUS release` esegue i test e, quando viene pubblicato un tag `vX.Y`, genera:
- un archivio `NEXUS_AI_X_Y.zip` contenente il programma, senza database utente;
- `latest.json` con versione, URL e digest SHA-256 per il downloader.

**Stato attuale:** codice e release iniziali pubblicati. La V2.6 aggiunge la verifica cronologica 70/30, con indicatori riscaldati esclusivamente da candele precedenti, e mostra quando il numero di operazioni è insufficiente per valutare la strategia. Non introduce nuovi agenti AI né dati WHALE/SHILL.

Il downloader locale non installa codice senza conferma. Per essere sicuro contro un account GitHub compromesso, il digest SHA-256 da solo non basta: bisogna verificare anche la provenienza delle release e proteggere l'account GitHub con 2FA.

## Preparazione del codice

Mettere nella radice del repository `src/`, `tests/`, `updater.py`, `migrate.py`, `updates.json`, `AVVIA_WINDOWS.ps1`. Non caricare `nexus.sqlite3`, `backups/`, `pending_update/`, file `.env`, segreti e wallet. Eseguire i test con:

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

Il canale di aggiornamento previsto è:
`https://raw.githubusercontent.com/manuQ001/NEXUS-AI-Trading/main/latest.json`

La V2.4.1 contiene il downloader compatibile con i redirect di GitHub Releases. Gli aggiornamenti vengono scaricati in un'area temporanea, ma si installano solo con conferma e server chiuso: `py updater.py --apply-staged`. La V2.5 corregge anche l'importazione dei moduli in questo comando. Il database locale non deve essere pubblicato.

## Verifica delle modifiche

Il workflow `Test NEXUS changes` esegue i test su ogni push a `main`. Pubblicare una release solo dopo esito positivo. La validazione 70/30 usa lo stesso dataset limitato di Kraken e **non è una prova indipendente di redditività**: la strategia non viene ottimizzata sul primo segmento e possono esserci pochi trade o dati insufficienti. Il saldo virtuale di €150 e il database locale non sono toccati da questi test.

## Sviluppo dopo 2.5 (non ancora rilasciato)

Le modifiche al ramo `main` sono in preparazione, non vengono installate sul PC finché non è pubblicato un nuovo tag GitHub. Il sistema accumula nel database locale `market_history` candele 5m BTC/ETH **solo dopo aver ricevuto feed Kraken valido**; non recupera retroattivamente oltre il limite dell'API pubblica. `/api/history` mostra la copertura; backtest e validazione 70/30 preferiscono lo storico archiviato, ripiegando sul feed recente se insufficiente. Nessun acquisto reale, nessuna nuova API key, nessun cambiamento di portafoglio o saldo.

Lo storico non rende affidabile la strategia da solo: controllare intervalli mancanti, numero di trade, costi stimati e test su altri regimi di mercato.

## Agente AI locale facoltativo (sviluppo non ancora rilasciato)

La schermata `Analisi AI locale` richiama `GET /api/ai-review?symbol=BTC` (oppure ETH) su richiesta esplicita. Il modello viene raggiunto **esclusivamente** sull'indirizzo `127.0.0.1:11434` con l'API Ollama `POST /api/generate`, `stream:false` e `format:"json"`. Nessun costo API cloud, ma il modello deve essere installato e può richiedere memoria e CPU/GPU.

Per abilitarlo in **una nuova PowerShell** dopo aver installato Ollama e scaricato un modello adatto alle risorse del PC:

```powershell
$env:NEXUS_OLLAMA_MODEL = "nome-del-modello-installato"
py .\src\server.py --no-browser
```

Per disabilitare: chiudere il server e riavviarlo senza la variabile (`Remove-Item Env:NEXUS_OLLAMA_MODEL`). Senza configurazione il pannello mostra `disabled`, non effettua chiamate di rete. Il modello riceve soltanto un piccolo riepilogo numerico delle decisioni dei moduli a regole, non il portafoglio o il database; non scrive sul disco e non modifica le decisioni. Non ha accesso a strumenti di trading né a wallet. I testi generati non sono segnali verificati e non provano redditività.

**Mai abilitare ordini reali con output di modello non verificato.** WHALE/SHILL non ricevono dati inventati e restano inattivi finché non saranno collegate fonti affidabili.
