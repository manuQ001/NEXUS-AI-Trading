"""Upgrade an existing NEXUS 2.6 installation to signed-by-hash 2.7 release.

Run this helper *inside the existing 2.6 folder* with NEXUS stopped.
Downloads only the fixed v2.7.0 release URL from GitHub, verifies the SHA256
in the official manifest, runs all shipped tests, backups DB and current code,
then installs every required module with rollback on copy errors.
No wallet credentials or real exchange orders.
"""
import ast
import hashlib
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path.cwd().resolve()
MANIFEST_URL='https://raw.githubusercontent.com/manuQ001/NEXUS-AI-Trading/main/latest.json'
RELEASE_PREFIX='https://github.com/manuQ001/NEXUS-AI-Trading/releases/download/v2.7.0/'
EXPECTED_VERSION='2.7.0'
MAX_ZIP=5*1024*1024
SAFE_HOSTS={'github.com','raw.githubusercontent.com','release-assets.githubusercontent.com'}


def download(url, *, limit):
    if urlsplit(url).scheme!='https':
        raise ValueError('È richiesto HTTPS')
    req=urllib.request.Request(url,headers={'User-Agent':'NEXUS-Verified-Upgrade/2.7'})
    with urllib.request.urlopen(req,timeout=35) as response:
        final=urlsplit(response.geturl())
        if final.scheme!='https' or final.hostname not in SAFE_HOSTS and not (
                final.hostname or '').endswith('.githubusercontent.com'):
            raise ValueError('Redirect fuori da GitHub')
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Download supera il limite dimensionale')
    return data


def files_from_package(base):
    """Read the literal list in the tested updater without executing it."""
    source=(base/'updater.py').read_text('utf-8')
    for statement in ast.parse(source).body:
        if isinstance(statement,ast.Assign) and any(
                isinstance(target,ast.Name) and target.id=='FILES'
                for target in statement.targets):
            files=ast.literal_eval(statement.value)
            if not isinstance(files,list) or len(files)<25 or len(files)!=len(set(files)):
                raise ValueError('Manifest file non valido')
            for name in files:
                p=Path(name)
                if not isinstance(name,str) or p.is_absolute() or '..' in p.parts or '\\' in name:
                    raise ValueError('Percorso non ammesso')
                if not (base/p).is_file():
                    raise ValueError('Modulo obbligatorio assente: '+name)
            for necessary in ('src/external_ai.py','src/hypothesis.py',
                              'src/research_journal.py','tests/test_hypothesis.py'):
                if necessary not in files:
                    raise ValueError('Pacchetto 2.7 incompleto')
            return files
    raise ValueError('FILES non trovato nel pacchetto')


def stop_check():
    # This port is exclusively bound by the local NEXUS dashboard.
    with socket.socket() as sock:
        sock.settimeout(.5)
        if sock.connect_ex(('127.0.0.1',8765))==0:
            raise ValueError('Chiudi prima NEXUS con CTRL+C: porta 8765 occupata')


def main():
    if not (ROOT/'src/core.py').is_file() or not (ROOT/'updater.py').is_file():
        raise ValueError('Apri PowerShell nella cartella principale della tua NEXUS 2.6')
    installed=(ROOT/'src/maintenance.py').read_text('utf-8')
    if not re.search(r"VERSION\s*=\s*['\"]2\.6\.0['\"]",installed):
        raise ValueError('Questo script è esclusivamente per NEXUS 2.6.0')
    stop_check()
    manifest=json.loads(download(MANIFEST_URL,limit=16384))
    if manifest.get('version')!=EXPECTED_VERSION:
        raise ValueError('Release 2.7 non ancora pubblicata: nessuna modifica applicata')
    url=manifest.get('zip_url','')
    expected=manifest.get('sha256','')
    if not isinstance(url,str) or not url.startswith(RELEASE_PREFIX) or not (
            isinstance(expected,str) and re.fullmatch(r'[0-9a-f]{64}',expected)):
        raise ValueError('Manifest 2.7 non valido')
    print('Scarico il pacchetto ufficiale NEXUS 2.7...')
    payload=download(url,limit=MAX_ZIP)
    if hashlib.sha256(payload).hexdigest()!=expected:
        raise ValueError('Checksum SHA-256 non corrisponde; annullo aggiornamento')
    with tempfile.TemporaryDirectory(prefix='nexus_upgrade_27_') as td:
        temp=Path(td)
        archive=temp/'release.zip'
        archive.write_bytes(payload)
        source=temp/'source'
        source.mkdir()
        with zipfile.ZipFile(archive) as zipped:
            seen=set()
            members=zipped.infolist()
            if sum(m.file_size for m in members)>MAX_ZIP:
                raise ValueError('Pacchetto troppo grande')
            for member in members:
                p=Path(member.filename)
                if (member.is_dir() or p.is_absolute() or '..' in p.parts or
                        '\\' in member.filename or member.filename in seen or
                        (member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError('Pacchetto non sicuro')
                seen.add(member.filename)
            zipped.extractall(source)
        files=files_from_package(source)
        if not re.search(r"VERSION\s*=\s*['\"]2\.7\.0['\"]",
                         (source/'src/maintenance.py').read_text('utf-8')):
            raise ValueError('Versione interna del pacchetto errata')
        print('Verifico tutti i test della 2.7...')
        checked=subprocess.run(
            [sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],
            cwd=source,capture_output=True,text=True,timeout=100)
        if checked.returncode:
            raise RuntimeError('Test del nuovo pacchetto falliti: '+checked.stderr[-1200:])
        stop_check()
        backup=ROOT/'backups'/('pre-2.7-'+time.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True,exist_ok=False)
        db=ROOT/'nexus.sqlite3'
        if db.exists():
            with sqlite3.connect(db) as old, sqlite3.connect(backup/'nexus.sqlite3') as saved:
                old.backup(saved)
        copied=[]
        try:
            for relative in files:
                if relative=='updates.json' and (ROOT/relative).exists():
                    continue
                src=source/relative
                dest=ROOT/relative
                old=backup/relative
                if dest.exists():
                    old.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(dest,old)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,dest)
                copied.append(relative)
        except Exception:
            for relative in reversed(copied):
                dest=ROOT/relative
                old=backup/relative
                if old.exists():
                    shutil.copy2(old,dest)
                else:
                    dest.unlink(missing_ok=True)
            raise
        print('NEXUS 2.7 installato. Storico e portafogli virtuali mantenuti.')
        print('Backup di codice e database:',backup)
        print('Avvio:',sys.executable,'src\\server.py')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('AGGIORNAMENTO NON APPLICATO:',exc)
        sys.exit(1)
