"""One-time 2.5 -> 2.6 migration: verified release, tests, backup, rollback.

Run in the EXISTING NEXUS 2.5 root after stopping its server.
No trading orders, no wallet credentials, no shell scripts.
"""
import hashlib
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path.cwd().resolve()
MANIFEST_URL='https://raw.githubusercontent.com/manuQ001/NEXUS-AI-Trading/main/latest.json'
EXPECTED_VERSION='2.6.0'
RELEASE_PREFIX='https://github.com/manuQ001/NEXUS-AI-Trading/releases/download/v2.6.0/'
MAX_ZIP=5*1024*1024

def download(url, limit):
    req=urllib.request.Request(url,headers={'User-Agent':'NEXUS-Verified-Migration/2.6'})
    with urllib.request.urlopen(req,timeout=30) as resp:
        final=resp.geturl()
        from urllib.parse import urlsplit
        host=urlsplit(final).hostname
        if urlsplit(final).scheme!='https' or host not in (
                'raw.githubusercontent.com','github.com','release-assets.githubusercontent.com'
        ) and not (host or '').endswith('.githubusercontent.com'):
            raise ValueError('Redirect a un host non autorizzato')
        payload=resp.read(limit+1)
    if len(payload)>limit:raise ValueError('File troppo grande')
    return payload

def main():
    if not (ROOT/'updater.py').is_file() or not (ROOT/'src/maintenance.py').is_file():
        raise ValueError('Apri prima la cartella principale di NEXUS 2.5')
    local=(ROOT/'src/maintenance.py').read_text('utf-8')
    if not re.search(r"VERSION\s*=\s*['\"]2\.5\.0['\"]",local):
        raise ValueError('Questa migrazione e solo per NEXUS 2.5.0')
    sock=socket.socket();sock.settimeout(.5)
    try:
        if sock.connect_ex(('127.0.0.1',8765))==0:
            raise ValueError('Chiudi prima NEXUS con CTRL+C: porta 8765 occupata')
    finally:sock.close()
    manifest=json.loads(download(MANIFEST_URL,16384))
    if manifest.get('version')!=EXPECTED_VERSION:
        raise ValueError('Release 2.6.0 non ancora pubblicata: aggiornamento annullato')
    url=manifest.get('zip_url')
    sha=manifest.get('sha256')
    if not isinstance(url,str) or not url.startswith(RELEASE_PREFIX):
        raise ValueError('URL release non autorizzato')
    if not isinstance(sha,str) or not re.fullmatch(r'[0-9a-f]{64}',sha.lower()):
        raise ValueError('Checksum non valido')
    print('Scarico NEXUS 2.6.0 dalla release ufficiale...')
    payload=download(url,MAX_ZIP)
    if hashlib.sha256(payload).hexdigest()!=sha.lower():
        raise ValueError('SHA256 errato: installazione bloccata')
    with tempfile.TemporaryDirectory(prefix='nexus_upgrade_') as td:
        temp=Path(td);archive=temp/'release.zip';archive.write_bytes(payload)
        source=temp/'release';source.mkdir()
        with zipfile.ZipFile(archive) as z:
            members=z.infolist()
            if sum(i.file_size for i in members)>MAX_ZIP:
                raise ValueError('Archivio eccessivo')
            for item in members:
                p=Path(item.filename)
                if (p.is_absolute() or '..' in p.parts or '\\' in item.filename or
                        item.is_dir() or item.external_attr >> 16 & 0o170000 == 0o120000):
                    raise ValueError('Contenuto ZIP non ammesso')
            z.extractall(source)
        sys.path.insert(0,str(source))
        import updater as new_updater
        files=list(new_updater.FILES)
        if not all((source/file).is_file() for file in files):
            raise ValueError('La release non include tutti i moduli')
        if not (source/'src/execution.py').is_file() or not (source/'src/orderbook.py').is_file():
            raise ValueError('Moduli 2.6 mancanti')
        print('Verifico tutti i test della release...')
        check=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],
                             cwd=source,capture_output=True,text=True,timeout=90)
        if check.returncode:
            raise RuntimeError('I test della release falliscono: '+check.stderr[-1000:])
        from datetime import datetime
        backup=ROOT/'backups'/('pre-2.6-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True,exist_ok=False)
        changed=[]
        db=ROOT/'nexus.sqlite3'
        if db.exists():
            with sqlite3.connect(str(db)) as old, sqlite3.connect(str(backup/'nexus.sqlite3')) as saved:
                old.backup(saved)
        print('Backup creato:',backup)
        try:
            for file in files:
                if file=='updates.json' and (ROOT/file).exists():
                    continue
                dst=ROOT/file;src=source/file
                if dst.exists():
                    copy=backup/file;copy.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(dst,copy)
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,dst)
                changed.append(file)
        except Exception:
            for file in reversed(changed):
                dst=ROOT/file;copy=backup/file
                if copy.exists():shutil.copy2(copy,dst)
                else:dst.unlink(missing_ok=True)
            raise
        print('NEXUS 2.6 installato. Database preesistente conservato.')
        print('Puoi avviare con: py -3.12 src\\server.py')
        print('Backup del codice e del database:',backup)

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('AGGIORNAMENTO NON APPLICATO:',error)
        sys.exit(1)
