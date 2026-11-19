# NEXUS AI Trading — Paper Trading

Progetto sperimentale per simulare operazioni su BTC/ETH e osservare token emergenti. **Nessun trading reale, nessuna leva e nessun wallet collegato.** Non esiste alcuna garanzia di guadagno.

## Release 2.8.1 — acquisti MEME autonomi con importo dinamico (paper only)

In modalità MEME AUTO il bot decide **sia se aprire una posizione sia quanto capitale virtuale allocare**, senza cliccare sul token. Gli ingressi variano tra €1,50 e €4,50 a seconda del minore tra liquidità e volume 24h osservati sia in Scout sia nella quotazione di conferma. Nessuna AI generativa controlla gli ordini.

Sono previsti: **massimo 10% del budget MEME iniziale per acquisto**, riserva iniziale di liquidità **20%**, massimo **3 nuovi ingressi per scansione**, massimo **8 posizioni contemporanee** e uscite automatiche simulate già esistenti. Il pulsante "Compra 3 €" non compare più in Meme Hunter; resta la vendita manuale di emergenza. La simulazione continua solo mentre il server locale è attivo e AUTO non è sospeso.

Queste euristiche non verificano la vendibilità o la sicurezza dei token e non garantiscono profitti. Il capitale CORE non viene usato per MEME; nessuna transazione reale è implementata.

## Release 2.8.0 — portafoglio MEME EUR unificato (solo simulazione)

La versione 2.8 usa **un solo portafoglio MEME virtuale in euro**, inizialmente da €45 e già compreso nei €150 complessivi; non crea un saldo demo USD aggiuntivo. Il vecchio storico demo USD resta archiviato nel database SQLite senza incidere sul saldo. Le nuove posizioni MEME sono denominate in EUR, con cambio USD/EUR giornaliero di riferimento e prezzi DEX Screener indicativi.

Il monitor MEME PAPER, quando il server locale è aperto e l'automazione è attiva, può aprire autonomamente fino a **3 posizioni da €3 per scansione**, fino a **8 posizioni simultanee**, controllare le quotazioni circa ogni 30 secondi e tentare uscite virtuali per stop −10%, target +20% o dopo 2 ore. La ricerca di nuovi candidati è prevista ogni 5 minuti. Queste sono **regole sperimentali**, non garanzie di esecuzione, vendibilità o rendimento; gli ingressi non avvengono se feed/prezzi/cambio non sono disponibili. Le commissioni simulate MEME sono 3% per lato.

**Nessuna transazione reale viene autorizzata.** Non vengono collegati wallet, chiavi private, exchange per ordini o servizi di pagamento. Conservare `nexus.sqlite3` prima di aggiornare. Per installazioni già alla 2.7, usare il sistema di aggiornamento verificato con backup integrato solo dopo la pubblicazione della release e l'esito dei test; chiudere NEXUS prima di applicarla.

## Release 2.7.0 — aggiornamento da NEXUS 2.6

La 2.7 aggiunge monitor autonomo delle candele chiuse mentre Python resta acceso, diagnosi dei WAIT, HEAD OF DESK/SNIPER/EXIT, AI esterna facoltativa solo consultiva e Diario AI prospettico. **PAPER ONLY**. Le API AI esterne restano disattivate senza chiave. Nessun miglioramento di redditività è garantito.

**Aggiornamento della cartella 2.6 esistente su Windows** (non estrarre una nuova copia sopra quella attuale):

1. Chiudi NEXUS nella finestra PowerShell con CTRL+C. Conserva la cartella originale e non cancellare `nexus.sqlite3`.
2. Apri PowerShell nella cartella principale della **tua NEXUS 2.6**, quella che contiene `updater.py`, `src` e `nexus.sqlite3`.
3. Scarica l'helper ufficiale e avvialo:

```powershell
Invoke-WebRequest 'https://raw.githubusercontent.com/manuQ001/NEXUS-AI-Trading/v2.7.0/upgrade_from_26.py' -OutFile '.\upgrade_from_26.py'
py -3.15 .\upgrade_from_26.py
```

4. Il programma verifica il manifest ufficiale 2.7.0, l'hash SHA-256 dello ZIP e l'intera suite di test prima di copiare. Esegue il backup SQLite e del codice in `backups/pre-2.7-...` e copia anche **tutti i nuovi moduli**, non previsti dall'updater della 2.6.
5. Solo se l'upgrade termina con successo, avvia `py -3.15 .\src\server.py` e controlla `http://127.0.0.1:8765`.

**Nota:** per il passaggio 2.6→2.7 usa l'helper qui sopra, **non** il vecchio `py updater.py --apply-staged` della 2.6, che ha un inventario incompleto dei nuovi moduli. Prima di procedere, verifica che la pagina della release ufficiale riporti la versione 2.7.0. Lo script non esegue il pacchetto senza averne verificato digest e test. L'hash nel manifest protegge da corruzioni accidentali, ma non è una firma crittografica indipendente dall'account GitHub.

## Aggiornamenti

Questo repository pubblico ospita il codice e le release ufficiali. La pipeline `Publish NEXUS release` esegue i test e, quando viene pubblicato un tag `vX.Y`, genera:
- un archivio `NEXUS_AI_X_Y.zip` contenente il programma, senza database utente;
- `latest.json` con versione, URL e digest SHA-256 per il downloader.

**Storico versioni:** la V2.6 aggiunge la verifica cronologica 70/30, con indicatori riscaldati esclusivamente da candele precedenti, e mostra quando il numero di operazioni è insufficiente per valutare la strategia. Non introduce nuovi agenti AI né dati WHALE/SHILL.

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

## Execution Engine condiviso (sviluppo, non ancora rilasciato)

Il modulo `src/execution.py` centralizza i costi di esecuzione per il paper trading e il backtest. Le operazioni BUY applicano slippage sfavorevole al prezzo di riferimento; le SELL applicano slippage sfavorevole nella direzione opposta. Le commissioni sono calcolate sul controvalore negoziato e il P/L realizzato include entrambe le commissioni e lo slippage di entrata e uscita. Il modulo valida prezzi, quantità e aliquote prima di calcolare un'esecuzione. La suite di test verifica, tra l'altro, che acquistare e vendere allo stesso prezzo di riferimento generi una perdita netta dovuta ai costi.

Il **prezzo di riferimento resta differente**: il paper live usa il miglior ask indicativo del Ticker Kraken, il backtest l'apertura della candela successiva; anche la modellazione temporale dell'uscita può differire. L'engine condiviso rende coerente l'aritmetica, **non dimostra ancora equivalenza delle esecuzioni**. Non riproduce liquidità effettiva, esecuzioni parziali o latenza di exchange. Nessun ordine reale viene introdotto.

## Execution Lab: scenari di liquidità e fill parziale (sviluppo non rilasciato)

`hypothetical_partial_fill` è un motore di stress test **sintetico e in sola lettura** che riceve una quantità richiesta, un prezzo centrale ipotetico, liquidità *disponibile sul lato opposto* già nota al chiamante, quota massima di partecipazione, spread, slippage e impatto sfavorevole ipotetico durante il ritardo. Se la liquidità disponibile è nulla, nessun fill è permesso; se non basta, l'ordine viene segnato come parziale e la quantità residua resta non eseguita. Gli input numerici sono convalidati. Il parametro `latency_bps` indica un **impatto di prezzo immaginato**, non una latenza misurata in millisecondi.

`GET /api/execution-study?symbol=BTC` (anche ETH) presenta in dashboard tre **scenari inventati** per un ordine di €25, usando solo l'ultima chiusura archiviata come prezzo indicativo. Tutti i volumi, gli spread e gli spostamenti di prezzo degli scenari sono assunzioni didattiche; **non** sono dati misurati di order book, né previsioni di eseguibilità. Non interagisce con i saldi, non genera ordini e **non modifica per ora il motore operativo del paper trading o il backtest**. L'eventuale collegamento richiederà dati L2 di profondità e un modello verificato sulla latenza.

## Kraken public order-book research (sviluppo non ancora rilasciato)

La dashboard può richiedere su richiesta esplicita il book pubblico `/0/public/Depth` di Kraken (`BTC/EUR`, `ETH/EUR`; massimo 20 livelli per lato), senza API key. Il modulo `src/orderbook.py` valida prezzo e volume di ogni livello, ordine delle ask/bid, spread positivo e risposta del server. `/api/orderbook-study?symbol=BTC` stima il costo medio ponderato (VWAP) di un acquisto o vendita per l'equivalente di €25 al midpoint e indica quanta quantità potrebbe essere assorbita dai livelli visibili. Lo studio è **in sola lettura** e non genera operazioni, non modifica il database né i controlli RISK. Se il volume aggregato è insufficiente, segnala esplicitamente un fill parziale: non inventa profondità oltre quella ricevuta.

**Limiti importanti:** un book REST è una fotografia osservata al momento della richiesta, non una sequenza sincronizzata di transazioni né una promessa di eseguibilità. I timestamp dei livelli non sono un timestamp globale di validità del book. Fra richiesta, risposta e invio ipotetico potrebbero mutare le quote e verificarsi cancellazioni, ordini concorrenti, commissioni diverse o scostamenti di prezzo. Non usare l'analisi per autorizzare operazioni autonome prima di aver implementato un modello di latenza/staleness e validazione con dati indipendenti.

## Controllo coerenza delle letture del book (sviluppo non rilasciato)

Il comando manuale «Leggi book Kraken» effettua **due richieste REST consecutive**. Per ognuna misura la durata della richiesta HTTP con un orologio monotono; registra l'istante locale di ricezione, confronta best bid e best ask e riporta la variazione in basis point. Segnala `CAUTION` quando la seconda risposta è stata ricevuta da più di 5 secondi, le letture sono distanti oltre 5 secondi, una chiamata dura oltre 2.500 ms, lo spread del secondo snapshot supera 50 bps, oppure una delle migliori quotazioni cambia oltre 25 bps. In assenza di anomalie mostra `PASS` **solo per la coerenza dei dati locali**, non come autorizzazione a operare.

La durata HTTP **non misura la latenza di un ordine** e l'ora di ricezione **non prova la vera età delle quotazioni presso Kraken**. Nessuno di questi controlli modifica RISK, SNIPER, wallet o database. L'uso è soltanto diagnostico, per una singola azione manuale in dashboard.

## Sviluppo 2.7 — HEAD OF DESK e qualità del book (non rilasciato)

Il consulto manuale `/api/agents?symbol=BTC` associa ora alla valutazione a regole una diagnosi di qualità ottenuta da **due snapshot REST** di Kraken. La nuova funzione pura `attach_market_quality` arricchisce il responso con `PASS`, `CAUTION` o `UNAVAILABLE`, lo spread osservato e l'eventuale variazione delle migliori quotazioni. In caso di book assente o `CAUTION`, sopprime un candidato BUY **soltanto nella visualizzazione consultiva**. `PASS` non rende un'operazione eseguibile né autorizzata.

**Importante:** il consulto non modifica `core.try_buy`, la gestione delle posizioni o i controlli RISK effettivi; l'analisi può richiedere fino a due chiamate HTTPS, che vengono effettuate solo quando si preme il pulsante. Nessuna decisione di esecuzione usa ancora lo stato del book: prima bisognerà progettare controlli separati sulla freschezza verificabile delle quotazioni e una politica di fill conservativa. Modifica in sviluppo sul ramo `main`, successiva alla release 2.6.

## Sviluppo 2.7 — SNIPER: studio indicativo di esecuzione, senza ordini

Quando `Consulta agenti` trova un candidato BUY preliminare senza veto RISK e il book Kraken supera i controlli locali, SNIPER produce un report **solo consultivo** per un budget di €25. Lo studio usa i **livelli ask osservati** nella seconda risposta Kraken, ma applica *ipotesi esplicite* di accessibilità del volume (10% per livello), slippage aggiuntivo (5 basis point), movimento avverso durante il ritardo (10 basis point) e commissione (0,25%). La quantità richiesta è dimensionata sul miglior ask con un cuscinetto per costi e fee. Calcola poi prezzo medio previsto, costo totale, volume potenzialmente coperto e residuo non coperto. Un book scarso genera `ESTIMATE_PARTIAL`; se la profondità più cara farebbe sforare il budget, `OVER_BUDGET`. In questi casi il **candidato visualizzato** viene soppresso e HEAD OF DESK mostra `execution_unverified`.

Si tratta di un *what-if* con liquidità pubblicata e ipotesi di costo inventate: **non è un replay della coda ordini, non è un fill eseguibile o predittivo, né misura la vera latenza di trading**. Un `ESTIMATE_FULL` non approva operazioni. RISK e il motore `try_buy` non sono modificati; la stima non compra e non vende, non scrive sul database. Gli endpoint restano locali.

## Sviluppo 2.7 — EXIT conservativo e replay dei tick (non rilasciato)

EXIT e il backtest condividono ora `assess_exit_bar`, una funzione pura che usa una **candela OHLC completata**: se nello stesso intervallo massimo e minimo raggiungono rispettivamente target e stop, attribuisce lo stop, perché l'ordine intrabar è ignoto. Se l'apertura osservata attraversa al ribasso lo stop, usa l'open peggiorativo; se attraversa al rialzo il target, non accredita un profitto oltre il target impostato. Non usa massimi/minimi delle barre iniziate prima dell'ingresso PAPER.

In caso di feed discontinuo oltre 10 minuti, il PAPER non apre una nuova posizione. Se la barra nuovamente osservata comprova uno stop, EXIT può contabilizzarlo; **non attribuisce un take-profit** sulla prima barra dopo il buco, perché gli intervalli mancanti potrebbero contenere movimenti contrari. Questo conserva il motivo `Stop loss` nel registro affinché funzioni il cooldown RISK di 30 minuti. I dettagli relativi ad ambiguità OHLC/gap sono registrati separatamente negli eventi. Il backtest espone anche i contatori `ambiguous_exit_bars`, `gap_stop_fills` e `targets_suppressed_after_feed_gap`.

La funzione `assess_exit_ticks` consente un **replay cronologico isolato** di tick con timestamp e prezzo, ignorando quelli anteriori all'ingresso: è pronta per futuri test con trade reali e verificati, ma **non è ancora collegata al motore paper**. Un trade print non dimostra di poter vendere al prezzo stampato e non è equivalente a un book bid/ask. La simulazione rimane basata sulle candele chiuse a 5 minuti e su costi stimati. Nessuna esecuzione reale o credenziale viene introdotta.

## Sviluppo 2.7 — monitor backend indipendente dalla dashboard

NEXUS avvia un thread di **monitoraggio autonomo quando parte `src/server.py`**. Il thread richiede a Kraken BTC/EUR ed ETH/EUR ogni **30 secondi** e elabora solo l'ultima candela a 5 minuti già chiusa, grazie a `process_candles`. La deduplicazione del timestamp impedisce di registrare due operazioni sulla stessa candela; il primo collegamento registra l'ultima candela come osservazione e **non ricostruisce ordini virtuali passati**. Resta in vigore il requisito di candela recente (entro 90 secondi dalla chiusura), ask attuale e veto RISK per ogni possibile BUY PAPER.

Il monitor funziona **senza la pagina aperta**, ma solo mentre Python/NEXUS resta in esecuzione, con Internet disponibile e il computer sveglio. Non è un servizio Windows, non sopravvive a spegnimento o sospensione, non invia notifiche e non contiene ordini reali. La dashboard ora esegue ogni 30 secondi solo `/api/state` (senza ulteriori richieste a Kraken o nuovi trade). Il pulsante manuale «Aggiorna mercato» resta disponibile e condivide il lock con il monitor. La sezione del feed indica l'ultimo controllo riuscito dal monitor e segnala errori.

SEARCH conserva **le stesse regole di ingresso** (incrocio dal basso EMA 9/21 sull'ultima candela chiusa, RSI 45–70, ATR positivo), ma le motivazioni `WAIT` sono dettagliate e includono codici `EMA_NO_CROSS`, `RSI_OUT_OF_RANGE`, `ATR_INVALID` e `INSUFFICIENT_HISTORY`. Nessun filtro è stato allentato per forzare operazioni. La frequenza di ingressi e la profittabilità non sono garantite.

## Sviluppo 2.7 — Agent Intelligence: coordinamento HEAD OF DESK

Il protocollo consultivo `coordinate_advisory` confronta in modo **deterministico** il segnale di SEARCH, il veto preliminare RISK, la qualità del book Kraken e la stima di profondità SNIPER. Restituisce un responso spiegabile (`WAIT`, `RISK_VETO`, `AWAIT_BOOK`, `MARKET_NOT_VERIFIED`, `EXECUTION_NOT_VERIFIED`, `NO_CANDIDATE`, `PRELIMINARY_CANDIDATE`) o `INCONSISTENT` in presenza di contraddizioni esplicite. Ogni responso include la motivazione, l'elenco dei pareri e gli eventuali codici di conflitto. Prima che il book venga interrogato si usa `AWAIT_BOOK`, non si presume che sia affidabile. La dashboard rende visibili il verdetto e le contraddizioni quando si preme **Consulta agenti**.

Questo coordinamento è **solo analitico**: `execution_authorized` rimane sempre `false`. Il codice non modifica `try_buy`, le condizioni EMA/RSI, il portafoglio o il database, e non permette a un modello linguistico di emettere ordini. Anche `PRELIMINARY_CANDIDATE` significa soltanto che i pareri consultivi sono coerenti, non che l'operazione sia eseguibile o profittevole. WHALE e SHILL rimangono non collegati: non vengono inventati dati on-chain o social.

## Sviluppo 2.7 — AI esterna facoltativa per SEARCH e HEAD OF DESK

L'advisor esterno usa la **OpenAI Responses API** con un'unica chiamata per produrre due punti di vista testuali separati: ricerca SEARCH e confronto HEAD OF DESK, più rischi e incertezze. Per attivarlo su Windows PowerShell (solo nella sessione corrente):

```powershell
$env:NEXUS_OPENAI_MODEL="gpt-4.1-mini"
$env:NEXUS_OPENAI_API_KEY="INSERISCI_LA_TUA_CHIAVE_IN_PRIVATO"
py -3.15 .\src\server.py
```

**Non inserire mai la chiave in GitHub, nei messaggi o nei file tracciati.** Usare una chiave di progetto limitata, con limiti di spesa configurati sul portale del fornitore. Il modello e l'accesso API richiedono una sottoscrizione/fatturazione API separata da ChatGPT; nessun pagamento è richiesto per continuare a usare il bot senza advisor. Se manca anche una sola variabile, l'advisor esterno non invia richieste. Se nessuna delle variabili OpenAI è presente, resta possibile configurare l'advisor locale preesistente con `NEXUS_OLLAMA_MODEL`. Non si attivano entrambi contemporaneamente.

Le chiamate esterne avvengono **soltanto** dopo click su «Consulta AI», mai in background, all'apertura della dashboard o durante il monitoraggio automatico. Il payload include solo un piccolo JSON di osservazioni di mercato, stati degli agenti e codici di conflitto, senza database, credenziali, saldi completi, cronologia personale o posizioni dettagliate. Il server invia un massimo di **550 token di output** per richiesta e consente **massimo 5 richieste per avvio del processo**. Il limite si azzera al riavvio e **non costituisce un limite di spesa**; usare comunque un limite sul proprio account del fornitore. Si applicano timeout, limite ai byte di risposta, schema JSON validato e blocco dei redirect. `store:false` viene richiesto per le risposte.

L'AI **non dispone di strumenti**, non invia ordini, non può modificare il database, non cambia `RISK`/`SEARCH`/`try_buy`, e il testo restituito non rientra mai nella logica di acquisto. Anche quando una risposta AI descrive un'opportunità, essa resta un commento incerto, **non una previsione attendibile o un'autorizzazione al trading**. Questo collegamento è pronto nel sorgente 2.7, non nella release 2.6.


## Sviluppo 2.7 — Diario AI e verifica successiva delle osservazioni

La dashboard include **Diario AI**, un registro di ricerca separato da wallet, posizioni e ordini. Dopo una richiesta manuale «Analisi AI» riuscita, il server prova a salvare provider, modello, responso testuale e **ultima candela Kraken chiusa** disponibile come riferimento. Il salvataggio è consentito soltanto mentre la candela è recente (massimo 5 minuti dalla sua chiusura), per evitare analisi retrodatate. I consulti disabilitati, falliti, con riferimento vecchio o duplicati non generano registrazioni. Il sistema non conserva la chiave API.

Quando il monitor vede nuove candele effettivamente **chiuse**, il modulo `research_journal.py` può annotare la variazione osservata del prezzo in basis point dopo **3 barre (15 minuti)** e **12 barre (60 minuti)** dal riferimento. Non usa candele future né dati ancora in formazione. Se mancano barre intermedie, registra `DATA_GAP` invece di interpolare risultati. Se i dati non sono ancora maturi, rimane `In attesa`. Il pulsante Diario AI consulta `GET /api/ai-research` senza inviare nuove richieste a modelli.

Le variazioni riportate **non sono un voto agli agenti**: l'AI attuale descrive opportunità e incertezza, non formula una previsione numerica/direzionale verificabile. Il diario mostra quindi soltanto l'andamento successivo accanto al testo originale, non percentuali di successo, profitti o performance attribuite all'AI. Il passo successivo sarà definire ipotesi misurabili *prima* degli esiti, in modo da poterle validare con campioni e costi adeguati.

Per evitare che pagamenti API siano attivati da richieste web accidentali, **l'analisi AI ora accetta soltanto POST dal pulsante della dashboard locale**, con intestazione personalizzata e controllo della provenienza; `GET /api/ai-review` non genera più chiamate AI. L'eventuale guasto del diario non cambia i trade PAPER e non cancella la risposta AI già prodotta. La 2.6 installata localmente rimane invariata.

## Sviluppo 2.7 — Ipotesi AI prospettiche e confronti direzionali

L'advisor OpenAI ora deve produrre **due ipotesi strutturate e predefinite**, riferite alle successive **3 candele (15 minuti)** e **12 candele (60 minuti)** a partire dalla candela di riferimento, con direzioni `UP`, `DOWN`, `FLAT` oppure `ABSTAIN` e una motivazione breve. `ABSTAIN` è la risposta corretta quando il modello non dispone di evidenze sufficienti. L'ordine degli orizzonti, la completezza dei campi e le direzioni ammesse sono validati prima di accettare la risposta. Per ora Ollama locale resta consultivo **senza ipotesi strutturate**, quindi non viene valutato come previsore.

Il diario SQLite conserva le ipotesi **insieme al testo originale**, quando la candela è recente. Il codice migra i diari esistenti aggiungendo la colonna opzionale `hypotheses_json` senza riscrivere le registrazioni vecchie: quelle restano senza un risultato direzionale. Quando le candele future sono chiuse e senza intervalli mancanti, confrontiamo le direzioni con una **fascia neutra fissata prima dell'esito di ±10 basis point** (`UP` sopra +10 bps, `DOWN` sotto -10 bps, `FLAT` in mezzo). Il risultato può essere `MATCH`, `MISMATCH`, `PENDING`, `DATA_GAP` o `ABSTAINED`; un'astensione non viene conteggiata come successo né errore. Non ci sono profitti simulati inventati, né prezzi di esecuzione, né autorizzazioni BUY/SELL, né analisi retroattiva per adattare la previsione.

**Avvertenza metodologica:** il confronto indica soltanto concordanza con un successivo movimento di prezzo, NON un rendimento netto, una probabilità affidabile di successo né un vantaggio statistico. Prima di usare questi risultati per decidere cambiamenti strategici serviranno un campione numeroso, un confronto con baseline semplici, periodi fuori campione, costi operativi e controllo della dipendenza tra previsioni sovrapposte.
