"""Manual, offline, hash-verified atomic code updater; preserves DB; never executes downloaded package."""
import argparse, hashlib, json, shutil, sys, tempfile, zipfile, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=[
    'src/core.py','src/server.py','src/dashboard.html','src/selftest.py',
    'src/maintenance.py','src/backtest.py','src/downloader.py',
    'src/agents.py','src/meme_agents.py','src/meme_live.py','src/execution.py','src/orderbook.py','src/meme_scout.py','src/rug_guard.py','src/whale_tracker.py','src/meme_demo.py','src/meme_auto.py','src/meme_portfolio.py','src/meme_intelligence.py','src/meme_desk.py','src/meme_mints.py','src/meme_prices.py',
    'src/external_ai.py','src/research_journal.py','src/hypothesis.py',
    'tests/test_orderbook.py','tests/test_meme_live.py','tests/test_agents.py','tests/test_meme_agents.py','tests/test_execution.py',
    'tests/test_backtest.py','tests/test_core.py','tests/test_maintenance.py',
    'tests/test_downloader.py','tests/test_external_ai.py','tests/test_monitor.py',
    'tests/test_ai_http.py','tests/test_research_journal.py','tests/test_hypothesis.py',
    'tests/test_upgrade_26.py','tests/test_meme_scout.py','tests/test_rug_guard.py','tests/test_whale_tracker.py','tests/test_meme_demo.py','tests/test_meme_http.py','tests/test_meme_intelligence.py','tests/test_meme_desk.py','tests/test_meme_mints.py','tests/test_meme_prices.py','tests/test_meme_auto.py','tests/test_meme_portfolio.py',
    'updater.py','README.md','updates.json',
    'migrate.py','upgrade_from_25.py','upgrade_from_26.py',
    'AVVIA_WINDOWS.ps1','AVVIA_ANTEPRIMA_WINDOWS.bat',
    'SCARICA_E_AVVIA_ANTEPRIMA.bat'
]
MAX_ZIP=5*1024*1024

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for x in iter(lambda:f.read(65536),b''):h.update(x)
    return h.hexdigest()

def safe_package(z, temp):
    with zipfile.ZipFile(z) as archive:
        names=archive.namelist()
        for item in archive.infolist():
            path=Path(item.filename)
            if item.is_dir():continue
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or item.file_size>MAX_ZIP:raise ValueError('Pacchetto non sicuro')
        if sum(i.file_size for i in archive.infolist())>MAX_ZIP:raise ValueError('Archivio troppo grande')
        archive.extractall(temp)
    candidates=[temp]+[p for p in temp.iterdir() if p.is_dir()]
    base=next((p for p in candidates if all((p/f).is_file() for f in FILES)),None)
    if not base:raise ValueError('Pacchetto non compatibile con NEXUS 2.2')
    return base

def install(z, expected):
    z=Path(z).resolve()
    if not z.is_file():raise ValueError('ZIP non trovato')
    if sha256(z).lower()!=expected.lower():raise ValueError('SHA-256 non corrisponde: aggiornamento bloccato')
    # Server must be shut down; SQLite lock probe alone is not a reliable indication.
    import socket
    s=socket.socket();s.settimeout(.4)
    try:
        if s.connect_ex(('127.0.0.1',8765))==0:raise ValueError('Chiudi il server NEXUS (CTRL+C) prima di aggiornare')
    finally:s.close()
    with tempfile.TemporaryDirectory(prefix='nexus_update_') as t:
        base=safe_package(z,Path(t))
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],cwd=base, capture_output=True,text=True,timeout=50)
        if result.returncode:raise RuntimeError('Test della nuova versione falliti: '+(result.stderr[-1200:]))
        backup=ROOT/'backups'/time.strftime('%Y%m%d-%H%M%S')
        backup.mkdir(parents=True,exist_ok=False)
        copied=[]
        try:
            for file in FILES:
                dest=ROOT/file
                if file=='updates.json' and dest.exists():continue
                if dest.exists():
                    old=backup/file;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(base/file,dest)
                copied.append(file)
        except Exception:
            for file in copied:
                dest=ROOT/file;old=backup/file
                if old.exists():shutil.copy2(old,dest)
                elif dest.exists():dest.unlink()
            raise
        return backup

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Installa un aggiornamento verificato offline, con backup e rollback del codice')
    p.add_argument('zip',nargs='?',help='Pacchetto ZIP di rilascio (facoltativo usando --apply-staged)')
    p.add_argument('--sha256',help='SHA-256 comunicato dal canale di rilascio fidato')
    p.add_argument('--apply-staged',action='store_true',help='Applica pacchetto già scaricato, dopo aver fermato il server')
    args=p.parse_args()
    try:
        if args.apply_staged:
            sys.path.insert(0,str(ROOT/'src'))
            from downloader import read_staged
            staged=read_staged()
            if not staged:raise ValueError('Nessun aggiornamento verificato pronto')
            print('Applico versione', staged['version'])
            result=install(staged['path'],staged['sha256'])
        else:
            if not args.zip or not args.sha256:raise ValueError('Indica ZIP e --sha256 oppure --apply-staged')
            result=install(args.zip,args.sha256)
        print('Aggiornamento completato; backup del codice in:',result)
    except Exception as exc:print('Aggiornamento NON applicato:',exc);sys.exit(1)
