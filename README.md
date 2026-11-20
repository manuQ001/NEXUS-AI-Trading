## NEXUS 3.13.0 — Decision Timeline live

La scheda **Terminale → Live Desk** integra **Decision Timeline**:
un elenco animato e filtrabile con eventi realmente registrati in
SQLite, tratti da tre fonti locali gia operative:

- `meme_auto_journal`: decisioni e azioni PAPER, inclusi il blocco Risk
  e le valutazioni dei ruoli. Un `AUTO_BUY` o `AUTO_SELL` e un ordine
  virtuale del simulatore, non una transazione blockchain.
- `meme_scan_decisions`: token osservati con esiti e ragioni dei filtri
  dello scanner. Un token esaminato non e stato necessariamente acquistato.
- `meme_shadow_signals`: segnali teorici e risultati a cinque minuti
  quando valutabili. Non equivalgono a un ordine PAPER o reale.

La dashboard puo filtrare gli eventi per **Scanner, Shadow, Risk,
PAPER, Decisioni**. Ogni record ha un identificatore stabile basato
sulla riga del database, una fonte esplicita e l'orario di registrazione.
L'animazione di ingresso avviene solo per nuovi record, non al semplice
refresh di una pagina o per i heartbeat di rete. Sono mostrati fino
a 30 record recenti, letti dal nuovo endpoint read-only
`GET /api/meme-decision-timeline`, e aggiornati quando arrivano eventi
SSE significativi o con controllo periodico ogni 12 secondi.

**Il componente NON crea eventi, ordini, quotazioni o segnali.
Non aggiunge feed a pagamento, non richiede wallet, non modifica
portafoglio o Risk Lock.** I ruoli dello scanner restano regole
diagnostiche e non modelli LLM indipendenti. Nel rispetto delle
preferenze di accessibilita `prefers-reduced-motion`, le animazioni
vengono disabilitate.

## NEXUS 3.12.2 — Correzione grafico "Failed to fetch"

Quando il Market Pulse mostra prezzi realmente osservati ma il grafico
candlestick segnala `Failed to fetch`, la causa puo essere la richiesta
HTTP separata per `/api/meme-market-candles`. Ora il backend aggrega
i campioni OHLC di **1 minuto e 5 minuti** gia presenti in SQLite nella
risposta esistente di `GET /api/meme-market-pulse`:
`quotes[].sampled_candles_1m` e `quotes[].sampled_candles_5m`.
Il frontend sceglie localmente i campioni del token e del timeframe senza
una seconda richiesta HTTP, quindi senza un'altra opportunita di errore
`Failed to fetch` in ogni ciclo di aggiornamento.

Restano validi i limiti delle candele campionate: solo letture REST
realmente registrate, dati vecchi segnalati, periodi mancanti non
inventati, nessun volume per candela inventato. L'endpoint autonomo
`/api/meme-market-candles` rimane disponibile per la diagnostica,
ma non e necessario per disegnare il grafico nella dashboard.

Nessun nuovo provider, nessuna nuova richiesta esterna, nessuno sblocco
di MEME AUTO o del Risk Lock e nessuna modifica al portafoglio.
Un server locale non aggiornato alla 3.12.2 deve essere riavviato
dopo l'installazione: in assenza delle nuove serie il frontend mostra
una nota esplicita sulla versione mancante invece di inventare prezzi.

## NEXUS 3.12.1 — Diagnostica "Nessuna quotazione disponibile"

La sezione Prezzi ora distingue **AUTO_SUSPENDED**, **WAITING_FIRST_SCAN**,
**NO_OBSERVED_QUOTES**, **STALE_QUOTES** e **OBSERVED_QUOTES**. Il messaggio
della dashboard indica lo stato reale del monitor REST, l'ora dell'ultima
scansione, quante quote sono state effettivamente ricevute nell'ultimo
ciclo, eventuali errori e la loro causa disponibile. Il grafico non
inventa candele: se lo scanner non ha ancora registrato prezzi, mostra
chiaramente il motivo noto.

Per diagnostica diretta, aprire sul PC dove gira il server:
`http://127.0.0.1:8765/api/meme-market-pulse`. Cercare
`quote_status`, `quote_explanation`, `auto_enabled`, `last_scan`,
`monitor.last_success` e `monitor.errors`.

Un Risk Lock che blocca nuovi BUY e diverso dalla sospensione completa
di MEME AUTO: il primo non disabilita la sola osservazione, la seconda
ferma anche il monitor REST. Questa release **non cambia** tali regole:
non abilita AUTO, non sblocca BUY, non crea dati falsi, non installa nuovi
provider, non modifica portafoglio o database di trading.

## NEXUS 3.12.0 — Market Chart Pro (OHLC da osservazioni REST)

La scheda **Prezzi** nel Terminale NEXUS adesso mostra un grafico OHLC
con candele rialziste/ribassiste, scelta del token e intervalli 1m/5m.
Il grafico usa i record `meme_quote_reads` preesistenti, generati
quando il server legge realmente una quotazione DEX Screener REST.
Il nuovo endpoint locale e
`GET /api/meme-market-candles?address=<MINT>&interval=60`
(intervalli consentiti 60 o 300 secondi).

**Interpretazione corretta:** queste sono candele OHLC *campionate*,
NON candele exchange derivate da ogni trade. Open/high/low/close
rappresentano il primo, massimo, minimo e ultimo prezzo effettivamente
letto dal server in quel minuto o blocco di cinque minuti. La frequenza
delle letture dipende dal monitor, dalla rotazione dei token, dalla
disponibilita della fonte e dal fatto che NEXUS sia in esecuzione.
Un minuto senza letture REST viene omesso, non riempito artificialmente.
I prezzi immutati costituiscono comunque letture reali. I dati sono
conservati in memoria persistente SQLite esistente, senza cambiare
l'archivio o il numero di chiamate REST al provider.

La visualizzazione espone l'eta dell'ultima lettura, liquidita e volume
24h (snapshot indicativi del provider). Il **volume 24h NON e volume
della candela**. Il grafico non mostra un volume per barra inventato.
Candele/quotazioni non sono prezzi eseguibili, non dimostrano vendibilita
e non sono una prova di liquidita sufficiente per negoziare.

Il sistema preserva tutte le altre schede Live Desk, Shadow, Risk,
Agenti e Strumenti; Risk Lock, storico, portafoglio PAPER e divieto
di ordini reali rimangono invariati.

## NEXUS 3.11.0 — Clean Live Dashboard (sola interfaccia)

Interfaccia piu ordinata, navigazione minimale e tre viste primarie
(Terminale, Mercato, Performance); le vecchie voci restano raggiungibili
dal menu "Altre sezioni", senza eliminare funzionalita.

Nel Terminale, le schede **Live Desk**, **Prezzi**, **Shadow**, **Risk**,
**Agenti**, **Strumenti** isolano il contenuto rilevante; i pannelli
non vengono piu impilati sulla stessa pagina. La sezione Strumenti
mantiene i comandi manuali precedenti, incluso il portafoglio PAPER:
nessuna funzione e stata rimossa dal backend. L'header continua a
mostrare l'equity MEME e lo stato del motore.

Il Live Desk ha un nuovo **Event Stream** che aggiunge una card soltanto
dopo l'effettiva ricezione dal server di un evento SSE di tipo
PAPER_MINT, PAPER_PROFILE, PAPER_QUOTES o PAPER_JOURNAL. I semplici
heartbeat PAPER_TICK, il polling identico e il caricamento della pagina
**non simulano alcuna animazione di trading**. Massimo otto eventi recenti
nel nastro, senza nuovi database, richieste API o servizi a pagamento.

Palette dark meno dispersiva, navigazione responsive, focus visibile
per accessibilita e supporto `prefers-reduced-motion`. Le funzioni
Shadow, Risk e la sezione prezzi continuano a essere aggiornate dai
loro endpoint reali tramite il codice precedente. Il motore, i
controlli di rischio, il capitale e gli ordini restano invariati.

Nessuna transazione blockchain viene effettuata. Nessuna visualizzazione
di evento GoPlus equivale a certificazione di vendibilita o sicurezza.

## NEXUS 3.10.0 — Risk Intelligence (read-only evidence)

La dashboard MEME aggiunge la sezione **RISK INTELLIGENCE · SOURCE AUDIT**.
I dati volume/liquidita dello scanner vengono archiviati per massimo 350
token e sette giorni in una tabella dedicata. Il fatto che un token superi
il filtro di volume/liquidita NON verifica sicurezza, contratto, vendibilita,
rug pull, freeze, concentrazione o LP lock: l'interfaccia lo mostra
esplicitamente.

Il progetto possedeva gia il controllo manuale *Rug Guard / GoPlus Solana*;
ora e possibile far esaminare **in modalita sola lettura** fino a un
token non ancora controllato ogni 90 secondi, su richiesta esplicita
dell'utente. Per attivare, in PowerShell **prima di avviare il server**:

```powershell
$env:NEXUS_RISK_GOPLUS_ENABLED = '1'
py .\src\server.py
```

Il valore predefinito e *disabilitato* e non implica chiamate a GoPlus.
Si applica inoltre un massimo di 120 interrogazioni esterne per database,
anche dopo riavvii; non si attivano servizi a pagamento, chiavi o abbonamenti
in maniera automatica. Verificare le condizioni del provider prima di
abilitare i controlli. Un risultato GoPlus e attribuito a quella fonte
terza e non costituisce prova on-chain autonoma.

Risultati: `NOT_CHECKED`, `PROVIDER_ERROR`, `RISCHI_RILEVATI`,
`DATI_INCOMPLETI` oppure `NESSUN_FLAG_NEI_CAMPI_LETTI`.
Anche `NESSUN_FLAG_NEI_CAMPI_LETTI` **non equivale a SICURO**. Le
informazioni LP lock e sellability restano NON VERIFICATE.
API locale: `GET /api/meme-risk-intelligence`.

La nuova analisi NON modifica score Shadow 3.9, ordine delle decisioni
PAPER, capitale, saldo, portafoglio, comandi di trading o Risk Lock
persistente; non autorizza acquisti virtuali o reali. Nessuna credenziale
wallet viene richiesta.

## NEXUS 3.9.1 — Fair Shadow Rotation e verifica copertura

Correzione su richiesta: con sei segnali Shadow pendenti la versione 3.9.0
monitorava sempre i primi tre e poteva lasciare gli altri senza dati.

La nuova rotazione **round robin** ripartisce i tre controlli REST disponibili
ogni ~10 secondi fra **tutti** i segnali Shadow ancora pendenti. Il cursore
viene salvato nel database SQLite e sopravvive al riavvio; nessuna quota
fittizia viene generata e il numero di richieste per ciclo resta limitato.
Le posizioni aperte del portafoglio PAPER sono monitorate a parte con le
regole esistenti e non utilizzano questa rotazione.

Nel nuovo Shadow Lab vengono ora mostrate:
- **Copertura effettiva**: quote future trovate rispetto ai segnali conclusi,
  casi senza dati e loro percentuali.
- **Fasce di score 50–69, 70–84, 85–100**: numero di segnali valutabili,
  percentuale con variazione netta teorica positiva e variazione media netta
  teorica. I segnali senza prezzo futuro non vengono conteggiati come vittorie,
  perdite o come campioni valutati; sono contabilizzati separatamente.

I dati provengono da quote REST osservate, non da un feed blockchain
tick-by-tick. Le quote osservate non garantiscono possibilita di esecuzione,
vendibilita, slippage reale o rendimento. Lo scoring resta deterministicamente
basato su liquidita, volume ed eta di pool quando nota; non include
verifiche on-chain automatiche anti-rug.

**Protezione**: nessun ordine reale o acquisto Shadow, nessuna modifica al
portafoglio principale, e Risk Lock persistente invariato. Mantiene
compatibilita col database 3.9.0 tramite migrazione additiva del solo cursore.

## NEXUS 3.9.0 — Smart Decision & Shadow Trading (solo osservazione)

Nuovo **Shadow Lab** in MEME HUNTER e API locale `GET /api/meme-shadow`.
Non vengono eseguiti ordini, neppure nel portafoglio virtuale principale.
I segnali shadow sono un registro separato in SQLite:

- Un segnale puo nascere soltanto da un vero record dello scanner con
  prezzo valido, liquidita osservata >=10.000 USD, volume 24h >=20.000 USD
  e, se l'eta della pool e nota, eta >=30 minuti.
- Lo score e un criterio quantitativo locale e deterministico, non una
  rete neurale o un LLM. Non dimostra la sicurezza del token.
- Massimo 3 segnali per scan, 20 pendenti simultanei, cooldown 30 minuti
  per token. Nessun acquisto virtuale o reale.
- Dopo 5 minuti il motore cerca il primo *prezzo REST effettivamente letto*
  nella finestra tra minuto 5 e minuto 10. Se presente, restituisce
  variazione lorda e variazione netta TEORICA con costi modellati al 3%
  per lato. Se mancano i dati, segna `INSUFFICIENT_DATA`, non inventa
  un exit o un profitto.
- Prezzi REST immutati possono essere nuovi dati realmente ricevuti.
  Per questo l'archivio `meme_quote_reads` conserva letture con
  timestamp, separandole da `meme_quote_changes` (usato dai grafici
  soltanto per effettivi cambi di valore).
- Il monitor REST 3.8.1 privilegia i token con segnali pendenti, con
  il medesimo tetto di 3 controlli ogni ~10 secondi. Non installa nuove
  sottoscrizioni WebSocket a pagamento.
- Report: segnali pendenti, osservati, privi di dati, e quota di casi
  con variazione netta teorica positiva tra i record recenti osservati.

**Limiti:** lo shadow score non verifica wallet dev, smart money, rug,
permessi mint, LP lock o vendibilita su blockchain. La variazione osservata
non e un trade eseguibile; i risultati risentono della selezione e della
disponibilita delle quote. Non rappresentano un backtest corretto per
esecuzione o un rendimento reale.

**Sicurezza:** storico e saldo portafoglio MEME invariati, Risk Lock
persistente al 10%, nessun reset, nessuna chiave wallet, nessun ordine
reale o chiamata a provider a pagamento. Tutto funziona soltanto quando
NEXUS gira sul PC locale.

## NEXUS 3.8.1 — Active Market Pulse Hotfix

Nella 3.8.0 lo storico delle quote si aggiornava principalmente ogni
scansione (~60 secondi) o quando esistevano posizioni aperte. In assenza
di posizioni, i grafici potevano quindi apparire fermi.

La 3.8.1 introduce `meme_prices.refresh_watchlist`: in ogni ciclo
del motore MEME (circa 10 secondi, quando AUTO e attivo) vengono
ricontrollati **massimo 3 token** candidati realmente osservati negli
ultimi dieci minuti, con liquidita osservata almeno 10.000 USD e volume
24h almeno 20.000 USD. Le nuove richieste usano la fonte DEX Screener
REST gia presente. Le posizioni aperte continuano a essere monitorate
dal motore di trading esistente, senza duplicare il polling.

L'aggiornamento memorizza l'ora dell'ultima quota valida anche se il
prezzo e invariato; invece, l'evento di variazione `PAPER_QUOTES` e un
nuovo punto sul grafico esistono **solo per prezzi distinti ricevuti**.
Un feed che non cambia prezzo non deve dare l'impressione di nuovi tick.

La dashboard mostra l'ultimo controllo riuscito, il numero di token
verificati e gli eventuali errori del monitor. L'API locale
`GET /api/meme-market-pulse` restituisce anche questi metadati nella
chiave `monitor`. Il polling e limitato, non e un WebSocket di
prezzi o trade reali; il tempo di aggiornamento dipende dalla rete
e dalla capacita del provider.

Il monitor rispetta la sospensione esplicita di MEME AUTO. Se il Risk
Lock e attivo, i grafici continuano a essere osservati ma **nessun
acquisto virtuale viene sbloccato**. Nessuna modifica a commissioni,
stop, storico, saldo o ordini reali.

## NEXUS 3.8.0 — Market Pulse osservato, eventi SSE e analisi dei costi

NEXUS riceve i token PumpPortal/DEX Screener gia documentati nelle versioni
precedenti. Questa release NON dichiara di possedere un feed di trade/prezzi
WebSocket indipendente: il provider PumpPortal richiede un'API key e applica
tariffe ai dati delle transazioni `subscribeTokenTrade` dal 1 maggio 2026.
Nessuna sottoscrizione a pagamento viene attivata di nascosto.

La nuova sezione **MARKET PULSE** all'interno del Live Command Center mostra
prezzi USD DEX Screener REST realmente letti dal server, con ora di
osservazione, eta del dato, fonte e grafici SVG delle variazioni osservate.
Non crea valori intermedi, non simula tick on-chain o fill eseguibili, e
segnala i dati non aggiornati (oltre 45 secondi).

- Quando lo scanner REST valuta candidati, `meme_desk.record_scan` salva
  i prezzi validati nella nuova tabella `meme_quote_latest`. Ogni effettiva
  variazione, e solo quella, viene salvata in `meme_quote_changes`.
- Il motore PAPER salva gli stessi dati sui prezzi dei token attualmente in
  posizione; nessun cambio alle regole di BUY/SELL e di gestione del rischio.
- Un batch di cambi osservati genera `PAPER_QUOTES` sul canale SSE locale
  `/api/meme-events`; non viene generato per la ripetizione di un prezzo
  identico. La dashboard anima il passaggio solo su eventi reali.
- Il grafico conserva al massimo 36 campioni per token visualizzato;
  il database conserva 24 ore e un massimo di 900 variazioni totali.
- `GET /api/meme-market-pulse` restituisce 10 token piu recentemente
  osservati, i campioni e l'eta dei dati. Nessuna chiamata a un provider
  esterno viene effettuata da questo endpoint.

La sezione mostra inoltre il costo simmetrico ipotizzato del 3% per lato:
pareggio lordo di circa +6,19% e movimento lordo di circa +18,93% necessario
per un target NETTO +12% (assumendo stessa base FX e percentuali fisse),
mentre stop di movimento lordo -5% equivale a perdita netta stimata intorno
al -10,53%. Sono conti sul modello, non costi/slippage eseguibili reali.

**Protezione invariata:** il Circuit Breaker persistente della 3.6 resta
attivo anche dopo rimbalzi o riavvii; non viene toccata nessuna somma del
portafoglio, nessun reset, e nessuna sottoscrizione pagata o transazione reale
viene abilitata. I processi locali continuano solo mentre il PC esegue NEXUS.

Per un futuro feed di trade nativo serviranno provider, prezzi verificati e
una decisione esplicita su chiavi API e spesa massima. Nessuna credenziale
wallet o API fee deve essere condivisa nella dashboard.

## NEXUS 3.7.0 — Live Command Center + feed nuovi mint Pump.fun

Il terminale MEME include una nuova sezione **LIVE COMMAND CENTER**:
stato EventSource/SSE locale, WebSocket profili DEX Screener, nuovo WebSocket
PumpPortal per eventi di creazione token, stato motore PAPER, stream delle
ultime decisioni e osservazioni di nuovi mint. Gli elementi grafici si
illuminano e si animano **solo quando arrivano effettivi eventi dal server**.
Le animazioni sono disabilitabili automaticamente tramite
`prefers-reduced-motion` del sistema operativo. La dashboard non inventa
prezzi, operazioni, lanci o segnali per produrre movimento visivo.

**Due fonti diverse:**

- `meme_live.py`: profili pubblicati/aggiornati DEX Screener WebSocket;
  questi possono essere sottoposti a verifiche REST delle pair e ai filtri
  esistenti per un eventuale BUY *virtuale*.
- `meme_mints.py`: feed PumpPortal `subscribeNewToken` a costo zero per
  eventi di creazione di token Pump.fun/PumpSwap, senza chiave API, su singola
  connessione TLS con reconnect e bounded dedup. Mostra l'indirizzo, simbolo,
  nome, ora e origine del provider. Non equivale a una conferma indipendente
  RPC on-chain e **non abilita automaticamente alcun acquisto**. Non ascolta
  transazioni di mercato, token trade, account trade, o prezzi in streaming.
  I prezzi NEXUS rimangono quote indicative REST.

Endpoint locale in sola lettura: `GET /api/meme-mints`, che espone anche
connessione reale, ultimo messaggio, numero di eventi realmente osservati e
riconnessioni; eventi `PAPER_MINT` dal canale `/api/meme-events`.
L'EventSource aggiorna la console e innesca un breve impulso/animazione solo
dopo un pacchetto concreto, non per simulare attività.

**Limiti rilevanti:** questa fonte copre gli eventi riconosciuti di
creazione Pump.fun, non *tutti* i nuovi token/mint dell'intera rete Solana.
Le fonti on-chain indipendenti, i controlli di vendibilita, liquidita bloccata
e anti-rug automatici completi non sono ancora implementati. Il programma
non e un bot per denaro reale: nessuna private key, nessuna transazione
firmata, nessuna garanzia di esecuzione o rendimento.

La protezione drawdown persistente di NEXUS 3.6, gli stop e i database
storici rimangono invariati. Nessuna riattivazione dei BUY e nessun reset
di saldo.

## NEXUS 3.6.0 — Desk Control & Permanent Risk Lock (PAPER)

La versione aggiunge un pannello **DESK CONTROL** sotto Strategy Intelligence con
otto ruoli (SEARCH, RUG, SNIPER, RISK, WHALE, EXIT, SHILL, HEAD OF DESK).
Sono stati effettivi dei moduli correnti: non sono otto processi LLM
indipendenti. In particolare RUG/WHALE restano controlli on-demand e SHILL non
ha fonti social collegate; la dashboard indica esplicitamente questa mancanza,
anziché presentare attività o sicurezza inventate.

Ogni candidato restituito dallo scanner, REST o dal feed di profili WS, viene
analizzato e registrato nel nuovo registro SQLite `meme_scan_decisions`
(indirizzo, simbolo, fonte, liquidita, volume, prezzo, eta pool quando noti,
motivo tecnico dello scarto). Stati: **REJECTED**, **WATCH_ONLY** quando i filtri
quantitativi passano ma il drawdown blocca l'acquisto, **SCREENED** quando
occorrono ancora le verifiche quote, eventuale LLM e capitale. SCREENED non
significa BUY autorizzato e gli eventi di discovery non equivalgono a
transazioni sulla blockchain. Il registro non legge Telegram o wallet privati,
non aggiunge richieste API, conserva max 1000 record degli ultimi sette giorni.

**Blocco rischio persistente**: al raggiungimento del drawdown MEME del 10%
il parametro SQLite `meme_auto_state.risk_latched` viene fissato a 1. Un
rimbalzo dell'equity o un riavvio del server non sblocca automaticamente
nuovi acquisti; la normale funzione di monitoraggio/EXIT rimane attiva.
Nessun comando per azzerare il saldo o riprendere trading e stato introdotto
in 3.6.0. Si tratta di una scelta conservativa per poter valutare prima le
cause della perdita. I dati e i trade storici vengono conservati intatti.

API locale: `GET /api/meme-desk`. Il payload contiene stato feed, ruoli,
decisioni e conteggi reali provenienti dal DB locale. Controlli non verificati
come mint authority, blocco LP, vendibilita e fonti social rimangono non
verificati, indipendentemente dal numero dei ruoli.

**Limiti:** lo scanner e basato su DEX Screener profili WebSocket + REST,
non su tutte le creazioni token Solana. I prezzi rimangono quote indicative
REST, non market orderbook eseguibile. Nessun ordine reale e mai abilitato,
nessun profitto e garantito, e le nuove analisi non migliorano di per se la
performance storica.

## NEXUS 3.5.0 — Strategy Intelligence (solo PAPER)

Nuovo pannello Strategy Intelligence nel terminale MEME e endpoint locale
`GET /api/meme-intelligence`. Sono raccolte e rese leggibili due categorie
rigorosamente diverse:

1. **Storico operazioni gia chiuse:** accoppiamento dei BUY/SELL realmente
   registrati nel database PAPER per indirizzo; P/L realizzato registrato,
   stima dell'impatto dei costi simulati del 3% per lato, durata, variazione
   prezzo/FX e causale AUTO_SELL quando il diario contiene una corrispondenza
   con data e indirizzo. I BUY senza vendita e i SELL senza acquisto
   corrispondente sono segnalati separatamente, non reinterpretati come profitto.
   Le causali non identificabili sono marcate non attribuibili. Non e un
   backtest e non ricostruisce dati di mercato mancanti.
2. **Watchlist osservativa mentre il Circuit Breaker e attivo:** i candidati
   restituiti dalle scansioni gia effettuate vengono memorizzati con prezzo,
   liquidita, volume, data di prima/ultima osservazione e numero di
   osservazioni. Solo dopo almeno due osservazioni indipendenti viene
   mostrata una variazione rispetto alla prima. La watchlist non esegue
   ordini e non fa nuove chiamate di mercato; non finge fill, P/L o risultati
   ipotetici. Il database mantiene al massimo 400 indirizzi e scarta
   osservazioni non riviste da 48 ore.

Il limite del 10% di drawdown del portafoglio MEME iniziale rimane invariato,
come i filtri di ingresso, gli stop, la strategia EXIT, i dati SQLite e gli
ordini reali disabilitati. Nessun azzeramento del saldo e nessuna riattivazione
automatica degli acquisti viene introdotta da questa funzione; il circuito
preesistente continua a ricalcolarsi sull'equity virtuale.

Le statistiche storiche includono le operazioni delle versioni precedenti,
quindi non misurano di per se la performance della 3.5.0. La variazione di
prezzo dei token osservati non e un guadagno reale o virtuale eseguibile.

## NEXUS 3.4.0 — Strategia PAPER disciplinata

Prima di ogni BUY automatico MEME richiediamo almeno $10.000 di liquidita osservata e $20.000 di volume 24h, in aggiunta ai controlli preesistenti. Se l'età del pool è nota e inferiore a 30 minuti il candidato è rifiutato. Sono soglie sperimentali da verificare sui risultati, NON una garanzia di sicurezza, performance o vendita eseguibile. Il bot registra AUTO_REJECT quando una verifica di qualità fallisce.

Lo stop primario ora misura una caduta del PREZZO/FX osservato del 5% dall'ingresso, anziche una perdita netta del 6% già quasi interamente consumata dai costi simulati del 3% in ingresso e del 3% in uscita. Un secondo stop di emergenza si applica a perdita netta stimata del 15%; target netto, trailing e timeout restano invariati. Il cambiamento puo aumentare la perdita netta su un singolo trade, non garantisce di ridurla. Il modello costi resta invariato e prudenziale, non è una commissione verificata sul mercato.

Se l'equity MEME stimata scende al 90% o meno del capitale iniziale MEME (45 EUR), un circuito RISK blocca *nuovi* acquisti AUTO e segnala la causa nella dashboard, ma continua a monitorare e chiudere eventuali posizioni aperte. Il blocco viene ricalcolato da equity ad ogni ciclo (puo cessare se l'equity risale). Non azzera dati né reimposta lo storico. Il saldo del portafoglio resta separato da BTC/ETH.

Gli acquisti MANUALI di test non sono modificati da questi filtri AUTO; non usarli per aggirare il blocco di rischio. Il programma opera in sola simulazione, senza chiavi wallet, senza trading reale. Il vincolo di drawdown su prezzi REST indicativi non protegge contro slippage e gap. I risultati del periodo 3.3 e 3.4 devono essere misurati separatamente.

## NEXUS 3.3.0 — WebSocket discovery dei profili MEME (PAPER)

Il processo mantiene una connessione TLS WebSocket con il feed ufficiale DEX Screener dei **profili token** (/token-profiles/latest/v1), senza API key. Dopo il primo snapshot di baseline, gli indirizzi Solana mai visti sono messi in una coda bounded e controllati tramite il REST ufficiale dei pair token. Soltanto i candidati con dati validi entrano nella valutazione multi-agent e nei controlli di rischio PAPER. Il motore resta completamente virtuale; lo stream non esegue trade di per se.

Questa fonte **non** segnala tutti i mint Solana: indica profili pubblicati o aggiornati su DEX Screener e puo mostrare token vecchi appena aggiunti ai profili. Non fornisce prezzi tick-by-tick, trade on-chain, prove di sicurezza o vendibilita. Per conoscere ogni creazione token sul network occorre un provider Solana on-chain e decodifica degli eventi. Il primo messaggio WS stabilisce soltanto la baseline: non trasforma vecchi profili in "nuovi token".

I candidati in ingresso dal feed passano al motore entro il successivo controllo automatico (circa 10 secondi quando accessibile), con enrichment REST e un massimo di 30 profili per batch. Se il feed non e connesso, il normale scanner REST resta disponibile ogni 60 secondi. Lo stato connesso, l'ultimo messaggio, la coda e l'ultimo errore sono disponibili su /api/meme-live, e la dashboard indica se il feed e effettivamente online. Nessun contatore o movimento di prezzo viene inventato.

## NEXUS 3.2.0 — live engine events, senza eventi fittizi

Il MEME PAPER ora scansiona i candidati ogni 60 secondi (in precedenza 5 minuti), monitora i prezzi delle posizioni circa ogni 10 secondi (prima 15 secondi), e inoltra eventi del motore al browser con Server-Sent Events su /api/meme-events. Il browser usa aggiornamento periodico come riserva quando SSE non e disponibile.

L'attivita visualizzata e basata su dati del programma: ogni ciclo confermato genera PAPER_TICK, le nuove righe del diario provocano PAPER_JOURNAL, e variazioni osservate di prezzo significative (almeno 0,2% dall'ultima quota) sono riportate come PRICE_OBSERVED. Questi eventi non corrispondono a nuovi trade, e nessun ordine viene simulato artificialmente per movimentare il terminale. Gli acquisti e le vendite PAPER mantengono le soglie esistenti e possono essere assenti anche durante lo scanner attivo.

AVVERTENZA: aggiornamento della UI e flusso eventi SSE **non** significano prezzi Solana tick-by-tick. La fonte quote resta DEX Screener REST, con rate limit e possibilita di dati invariati, mancanti o non vendibili. La sicurezza on-chain non e garantita. La frequenza delle analisi LLM dipende dalla presenza di candidati e dal limite di 10 consulti per processo, non necessariamente ad ogni tick; la quota provider può costare denaro e il limite riparte dopo un riavvio.

## NEXUS 3.0.0 — MEME multi-agent desk

Il motore MEME PAPER consulta un comitato di agenti alla scansione: SEARCH, RISK, STRATEGIST, HEAD OF DESK, SNIPER e EXIT. La dashboard mostra separatamente la natura degli agenti: **RULE_AGENTS** (regole deterministiche, non intelligenza artificiale generativa) oppure **LLM_AGENT_REVIEW** (un modello IA realmente consultato).

Senza chiave API, il desk continua in modalita a regole e lo dichiara. Per abilitare opzionalmente l'analisi generativa in una sessione PowerShell impostare **prima dell'avvio** le variabili d'ambiente `NEXUS_MEME_AI_MODEL` e `NEXUS_MEME_AI_API_KEY` con un modello disponibile al proprio account OpenAI. Non mettere la chiave nel codice, nel browser o in un file da condividere. Questo usa chiamate API a pagamento e non e incluso nell'abbonamento ChatGPT; impostare un limite di spesa dal provider. Il limite locale di 10 chiamate per processo NON e un limite economico e si azzera riavviando il server.

Durante una scansione sono inviati al modello soltanto gli attributi numerici disponibili dei primi tre candidati, simbolo e indirizzo. Un unico consulto presenta quattro ruoli distinti: SEARCH, RISK, STRATEGIST e HEAD OF DESK; SNIPER ed EXIT restano eseguiti a regole. Un modello puo **votare contro** un candidato, ma non autorizzare ingressi che il motore di rischio non consentirebbe, impostare importi o inviare ordini reali. Se il consulto attivato fallisce, nessun nuovo ingresso viene aperto in quella scansione. I prezzi restano indicativi e la vendibilita NON verificata. Non esiste garanzia di profitto.

# NEXUS AI Trading — Paper Trading

Progetto sperimentale per simulare operazioni su BTC/ETH e osservare token emergenti. **Nessun trading reale, nessuna leva e nessun wallet collegato.** Non esiste alcuna garanzia di guadagno.

## NEXUS 2.9.0 — Autonomous Trading Terminal (solo trading virtuale)

La sezione MEME HUNTER ora include un terminale operativo che si aggiorna automaticamente ogni 2 secondi quando il browser è visibile. Mostra lo stato del motore autonomo, l'ultima scansione, le posizioni simultanee, il P/L virtuale stimato, un pronostico euristico per ogni posizione (rialzista/ribassista/incerto) e un registro delle decisioni con conteggio dei token analizzati/idonei, motivi di entrata/uscita e problemi del feed.

Il monitoraggio delle posizioni è eseguito dal server circa ogni 15 secondi; la ricerca di token resta ogni 5 minuti. Questi tempi non sono aggiornamenti exchange tick-by-tick. Gli snapshot DEX Screener REST sono prezzi indicativi, senza garanzia di freschezza della quotazione, liquidità negoziabile o possibilità di vendita. Le spiegazioni non sono consigli di investimento e non controllano direttamente l'esecuzione. Solo ordini virtuali; nessuna credenziale di wallet o trasferimento blockchain.

L'aggiornamento va installato solo dopo il superamento dei test Python e del controllo sintattico della dashboard JS. Il codice è revisionato prima del rilascio ufficiale. L'updater mantiene l'archivio SQLite esistente.

## Release 2.8.5 — pronostico descrittivo nelle posizioni MEME aperte

Ogni posizione virtuale mostra un segnale aggiornato automaticamente nella dashboard: RIALZISTA, RIBASSISTA, INCERTO o DATI_NON_RECENTI, accompagnato da spiegazione e affidabilità bassa/non valutabile. Il segnale è una *descrizione euristica* delle ultime due variazioni osservate (serve una sequenza di almeno tre prezzi diversi), non un modello predittivo né una probabilità di guadagno. Le richieste REST al provider non garantiscono freschezza del prezzo: quando mancano letture recenti si sospende il segnale. Nessuna decisione automatica di trading dipende da questo pronostico; restano le regole esistenti. Le osservazioni di prezzo vengono registrate in una piccola tabella SQLite per ogni posizione aperta e ripulite alla vendita. Test di regressione inclusi. Non sono collegati wallet reali.

## Release 2.8.4 — correzione acquisti MEME e test di regressione

Corretto il caricamento del capitale iniziale nel controllo dei limiti degli acquisti MEME virtuali: prima il codice interrogava il solo saldo cash e poi leggeva il campo initial mancante, provocando IndexError e impedendo l'aggiornamento dopo il fallimento dei test. Nuovo test automatico per verificare acquisti dinamici fino al 10% del capitale virtuale iniziale. Include le funzioni scalping e dashboard live della 2.8.3. Non modifica il file SQLite esistente.\n\n## Release 2.8.3 — MEME Scalper con vista live automatica (solo simulazione)

Nuove uscite MEME PAPER: stop loss a -6% netto stimato, take profit a +12% netto stimato, trailing stop attivo dopo +8% di rendimento netto massimo con distanza di 4 punti percentuali, e limite temporale di 15 minuti. Il picco del trailing è memorizzato in SQLite per sopravvivere ai riavvii; la vendita virtuale richiede sempre una nuova quotazione valida e non viene inventata quando manca il feed. Lo storico delle posizioni e il database esistenti restano intatti.

Il motore controlla i prezzi indicativi delle posizioni aperte circa ogni 15 secondi mentre il server è attivo. La dashboard, quando visibile, ricarica automaticamente portafoglio e stato AUTO ogni 2 secondi, senza pulsanti manuali. **Questo non è uno stream di tick real-time**: DEX Screener REST non garantisce una nuova quotazione né la sua effettiva negoziabilità a ogni richiesta. Una pagina aggiornata non rende più fresco un feed vecchio. Alcune uscite potrebbero avvenire più tardi delle soglie e i costi reali potrebbero essere diversi dal modello a 3% per lato.

Il sistema rimane PAPER ONLY senza wallet collegati, chiavi di scambio o ordini reali. Prima di valutare capitale reale, servono prezzi con timestamp affidabili, liquidità/quotazioni eseguibili e un backtest realistico.

## Release 2.8.2 — MEME Scout più ampio e diagnosi scansioni

MEME Scout considera fino a 30 profili Solana per scansione (in precedenza 16) e l'automazione non tronca più la selezione ai primi 12 candidati. Lo stato AUTO ora riporta quanti token hanno superato il filtro iniziale, o se la fonte non ha fornito alcun token. Non vengono eliminate le verifiche di liquidità, volume, prezzo, cambio o disponibilità in portafoglio.

La release include le allocazioni MEME virtuali variabili sviluppate nella 2.8.1. Restano invariati il limite di 8 posizioni, le protezioni del portafoglio e il divieto di inviare ordini reali. DEX Screener mostra solo un campione, non tutte le memecoin; l'ampliamento non garantisce nuovi ordini, accuratezza del prezzo o vendibilità.

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
