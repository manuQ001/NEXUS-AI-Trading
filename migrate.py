"""One-time in-place migration of older NEXUS 2.x installation, preserving user database."""
import sys,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=['src/core.py','src/server.py','src/dashboard.html','src/selftest.py','src/maintenance.py','src/backtest.py','src/downloader.py','tests/test_backtest.py','tests/test_core.py','tests/test_maintenance.py','tests/test_downloader.py','updater.py','README.md','updates.json']
def migrate(target):
    target=Path(target).resolve()
    if not (target/'src/core.py').is_file() or not (target/'src/server.py').is_file():raise ValueError('Cartella NEXUS precedente non riconosciuta')
    if ROOT==target:raise ValueError('Non aggiornare una cartella su se stessa')
    import socket
    sock=socket.socket();sock.settimeout(.4)
    try:
        if sock.connect_ex(('127.0.0.1',8765))==0:raise ValueError('Prima arresta NEXUS con CTRL+C nella vecchia PowerShell')
    finally:sock.close()
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],cwd=ROOT,capture_output=True,text=True,timeout=40)
    if result.returncode:raise ValueError('Nuovo codice non supera i test: '+result.stderr[-500:])
    backup=target/'backups'/time.strftime('migrazione-%Y%m%d-%H%M%S')
    backup.mkdir(parents=True,exist_ok=False)
    copied=[]
    try:
        for f in FILES:
            source=ROOT/f;dest=target/f
            if f=='updates.json' and dest.exists():continue
            if dest.exists():
                original=backup/f;original.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,original)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,dest);copied.append(f)
    except Exception:
        for f in copied:
            dest=target/f;original=backup/f
            if original.exists():shutil.copy2(original,dest)
            elif dest.exists():dest.unlink()
        raise
    return backup
if __name__=='__main__':
    if len(sys.argv)!=2:print('Uso: py migrate.py "PERCORSO_CARTELLA_NEXUS_2_1"');sys.exit(2)
    try:
        b=migrate(sys.argv[1]);print('Aggiornamento completato. Storico mantenuto; backup codice in:',b)
    except Exception as e:print('Aggiornamento non applicato:',e);sys.exit(1)
