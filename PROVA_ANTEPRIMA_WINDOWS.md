# NEXUS AI 2.6 — anteprima per Windows (PAPER ONLY)

Questa anteprima contiene gli sviluppi attualmente presenti sul ramo main. Non è ancora una GitHub Release ufficiale. Nessun ordine reale e nessuna chiave API.

## Installazione per prova senza toccare la 2.5

1. Chiudi NEXUS 2.5: nella sua finestra PowerShell premi **CTRL+C**.
2. Vai su https://github.com/manuQ001/NEXUS-AI-Trading e scegli **Code > Download ZIP**.
3. Estrai tutto lo ZIP in una nuova cartella, per esempio `Desktop\NEXUS-ANTEPRIMA`. **Non estrarlo sopra la cartella della 2.5.**
4. Apri la cartella estratta `NEXUS-AI-Trading-main` e fai doppio clic su `AVVIA_ANTEPRIMA_WINDOWS.bat`.
5. Se Windows non trova Python 3.12, verifica Python con `py -0p` nella PowerShell e installa Python 3.12 dal sito ufficiale.
6. Apri `http://127.0.0.1:8765` nel browser se la dashboard non si apre automaticamente.

La prima esecuzione crea un **nuovo** database `nexus.sqlite3` nel percorso della cartella di anteprima, con €150 virtuali e senza le posizioni storiche della 2.5. Il database della vecchia installazione non viene toccato. Per vedere lo storico nel nuovo programma, a NEXUS spento si può COPIARE (non spostare) il file `nexus.sqlite3` dalla vecchia installazione nella cartella principale dell'anteprima, dopo aver fatto un backup. Non sovrascrivere un database dell'anteprima che contenga prove da conservare.

## Cosa controllare

- Dashboard e prezzo live BTC/ETH (il WebSocket mostra trade effettivamente arrivati, non garantisce un tick ogni millisecondo).
- `Kraken Book`: risultati osservati su due letture pubbliche, qualità PASS/CAUTION, solo consultazione.
- `Execution Lab`: tre scenari sintetici che non riflettono la liquidità reale.
- `Analisi degli agenti`, `Backtest`, `Validazione`, `Verifica BUY/SELL/STOP`.
- Pannello RISK: limite acquisti giornalieri, cooldown e circuito Core.

I dati del book possono diventare indisponibili per problemi di rete o di API. **PASS non è un segnale d'acquisto.** La redditività non è stata dimostrata.

## Come uscire o tornare alla 2.5

Premi CTRL+C nella finestra della anteprima. L'installazione 2.5 è rimasta invariata, quindi puoi avviarla come prima. **Non eseguire contemporaneamente le due versioni:** entrambe usano la porta 8765.
