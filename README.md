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
