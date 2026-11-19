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

## Grafici live WebSocket (sviluppo non ancora rilasciato)

La dashboard mantiene lo storico delle **candele chiuse a 5 minuti** per gli indicatori e le decisioni del simulatore. In parallelo, quando la pagina è visibile, il browser apre `wss://ws.kraken.com/v2` e sottoscrive `trade` per `BTC/EUR` e `ETH/EUR`, senza autenticazione. I trade arrivano quando realmente eseguiti sull'exchange: **non esiste garanzia di un aggiornamento ogni millisecondo**. Il grafico live visualizza gli ultimi tick ricevuti, non ricostruisce ogni trade precedente all'apertura della pagina e non modifica le candele di trading. Aggiornamento visivo limitato a massimo 10 volte al secondo per non sovraccaricare il browser; riconnessione con backoff se si interrompe il WebSocket e indicatore che segnala dati non aggiornati.

Se la rete impedisce WebSocket, rimane il vecchio feed REST tramite aggiornamento periodico. L'orario riportato è quello del trade, non una misura garantita di latenza. Le decisioni di trading **restano legate alle candele chiuse**.

## Integrità delle simulazioni (sviluppo non ancora rilasciato)

Il motore paper rifiuta nuovi ingressi basati su una candela 5m che risulti già chiusa da oltre 90 secondi, oppure non ancora chiusa, e registra un veto RISK. Il backtest non apre nuove posizioni immediatamente dopo una discontinuità di storico. Fino all'ottimizzazione degli indicatori, il server limita il backtest alle ultime 1.500 candele archiviate per evitare calcoli quadratici potenzialmente molto lenti: il dato storico accumulato oltre questo limite **non viene cancellato**. Questo è un limite operativo temporaneo, non una validazione di redditività.

**Limite ancora da risolvere:** il simulatore corrente ipotizza una compilazione al prezzo di chiusura osservato, mentre il backtest usa l'apertura della candela successiva. Le due simulazioni non sono ancora perfettamente comparabili. Prima di usare il bot per valutazioni economiche attendibili occorrerà implementare un prezzo di esecuzione osservato e consolidare le regole di fill, slippage e latenze.

## Prezzo di esecuzione indicativo per il simulatore (sviluppo non rilasciato)

Il motore paper non simula più nuovi acquisti al prezzo della **precedente candela chiusa**. Quando scatta un segnale recente e i controlli RISK lo consentono, richiede il prezzo **ask indicativo** dall'endpoint pubblico Kraken Ticker e applica lo slippage stimato. Senza una risposta valida, oppure quando l'ask differisce di oltre l'1,5% dal prezzo di chiusura del segnale, non apre la posizione simulata. I test sintetici passano una quotazione sintetica, senza accesso di rete.

**Limiti:** il Ticker REST non garantisce la disponibilità o l'eseguibilità della quotazione, non include una misura verificata della sua età e non replica book, volume, ritardi o liquidità. Il backtest continua a usare l'apertura della candela successiva ed è perciò una stima con ipotesi diverse dal paper live. Sarà necessaria una verifica empirica prima di definire i due motori equivalenti. Nessun ordine reale può essere eseguito.

## Correzione EXIT: nessun movimento anteriore all'ingresso

Per i dati reali, una candela OHLC descrive l'intero intervallo di cinque minuti, ma non indica in quale istante siano stati raggiunti massimo e minimo. Se un acquisto virtuale si verifica a intervallo già iniziato, **EXIT non deve usare il massimo o minimo di quello stesso intervallo**: potrebbero precedere l'acquisto. Il simulatore ora ignora per le uscite le candele il cui timestamp di apertura precede `positions.opened_at`; valuta solamente intervalli iniziati dopo (o esattamente all'istante di) ingresso. I test sintetici confermano che questo impedisce chiusure retroattive inventate e permette uscite su intervalli successivi.

Questa scelta è prudente ma può ritardare un'uscita paper rispetto al mercato reale. Per una simulazione intrabar occorrono dati con granularità temporale maggiore e un modello di execution costi/latency separato, non un'assunzione favorevole sui massimi e minimi OHLC.

## Controllo centrale HEAD OF DESK → RISK → SNIPER (sviluppo non rilasciato)

Tutti gli ingressi paper, anche quelli che richiamano direttamente `try_buy`, passano dalla funzione di valutazione `assess_paper_order` senza scritture al database durante la verifica. Le condizioni includono: BTC/ETH soltanto, segnale BUY, ask Kraken presente e finito, scostamento massimo 1,5% dal close, ATR positivo, nessuna posizione già aperta, limite sulle perdite realizzate giornaliere (2% di €150), circuito di arresto per Core con disponibilità sotto il 90% del capitale Core iniziale (€105) quando non ci sono posizioni, budget di rischio teorico 0,5% del capitale virtuale complessivo (€0,75) e disponibilità comprensiva delle commissioni. I controlli restituiscono un motivo leggibile che HEAD OF DESK registra nel diario decisionale; nessun output di un agente LLM può aggirare questi controlli.

La schermata degli agenti mostra soltanto una **valutazione preliminare**. Senza una quotazione ask verificata, non autorizza né esegue ordini. Il limite di liquidità Core non equivale a una garanzia di drawdown massimo sul portafoglio e non impedisce perdite superiori ai limiti in presenza di gap, slippage e ritardi.

## RISK e HEAD OF DESK: controllo centralizzato (sviluppo non ancora rilasciato)

`assess_paper_order` è il solo controllo per autorizzare un nuovo ingresso virtuale; `try_buy` lo richiama obbligatoriamente. I modelli AI consultivi non hanno accesso all'esecuzione. Il veto avviene in assenza di un segnale BUY, di una quotazione valida, se una posizione è già aperta, in presenza di perdite realizzate giornaliere oltre il 2% del capitale iniziale, quando il capitale Core disponibile senza posizioni scende sotto il 90% iniziale, **dopo sei acquisti virtuali nello stesso giorno UTC** o nei **30 minuti successivi a uno stop loss**. Rimangono i limiti di quantità, spesa, ATR e commissioni. Le soglie sono euristiche sperimentali, non garantiscono un limite certo alla perdita.

HEAD OF DESK registra se l'operazione è stata effettivamente autorizzata e, in caso contrario, la motivazione del veto; la dashboard mostra alcuni contatori RISK in sola lettura. Nei test non vengono utilizzati wallet reali, chiavi di exchange o ordini autentici. Per verificare prestazioni e gestione del rischio resta necessario un confronto prolungato su dati di mercato indipendenti.
