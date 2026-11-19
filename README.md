# NEXUS AI Trading — Paper Trading

Progetto sperimentale per simulare operazioni su BTC/ETH e osservare token emergenti. **Nessun trading reale, nessuna leva e nessun wallet collegato.** Non esiste alcuna garanzia di guadagno.

## Aggiornamenti

Questo repository pubblico ospita il codice e le release ufficiali. La pipeline `Publish NEXUS release` esegue i test e, quando viene pubblicato un tag `vX.Y`, genera:
- un archivio `NEXUS_AI_X_Y.zip` contenente il programma, senza database utente;
- `latest.json` con versione, URL e digest SHA-256 per il downloader.

**Stato attuale:** repository inizializzato; il codice applicativo deve essere caricato prima di poter pubblicare una release. Nessun aggiornamento è ancora disponibile.

Il downloader locale non installa codice senza conferma. Per essere sicuro contro un account GitHub compromesso, il digest SHA-256 da solo non basta: bisogna verificare anche la provenienza delle release e proteggere l'account GitHub con 2FA.

## Preparazione del codice

Mettere nella radice del repository `src/`, `tests/`, `updater.py`, `migrate.py`, `updates.json`, `AVVIA_WINDOWS.ps1`. Non caricare `nexus.sqlite3`, `backups/`, `pending_update/`, file `.env`, segreti e wallet. Eseguire i test con:

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

Il canale di aggiornamento previsto è:
`https://raw.githubusercontent.com/manuQ001/NEXUS-AI-Trading/main/latest.json`

Non puntare l'installazione locale a questo URL prima che la prima release sia stata pubblicata e il downloader sia stato reso compatibile con i redirect di GitHub Releases.
