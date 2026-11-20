"""Offline test runner and cautious update discovery. Standard library only."""
import json, subprocess, sys, hashlib, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VERSION='4.3.0'
CONFIG=ROOT/'updates.json'

def run_tests(timeout=40):
    try:
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],cwd=ROOT,capture_output=True,text=True,timeout=timeout)
        return {'ok':result.returncode==0,'exit_code':result.returncode,'output':(result.stdout+'\n'+result.stderr)[-11000:],'isolated':True}
    except subprocess.TimeoutExpired:
        return {'ok':False,'error':'Test interrotti per timeout'}

def get_config():
    try:return json.loads(CONFIG.read_text('utf-8'))
    except (OSError,ValueError):return {}

def check_updates():
    url=get_config().get('manifest_url','')
    if not url:return {'configured':False,'version':VERSION,'note':'Nessun archivio di rilascio impostato. Gli aggiornamenti non possono arrivare automaticamente finchÃ© non viene configurato un indirizzo HTTPS verificato.'}
    if not isinstance(url,str) or not url.startswith('https://'):
        return {'configured':False,'error':'Il manifest deve usare HTTPS'}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'NEXUS-Paper-Only/2.2'})
        with urllib.request.urlopen(req,timeout=8) as response:
            if response.geturl()!=url:raise ValueError('Redirect non consentito')
            payload=response.read(16385)
        if len(payload)>16384:raise ValueError('Manifest troppo grande')
        m=json.loads(payload)
        if not isinstance(m,dict) or not all(k in m for k in ('version','zip_url','sha256')):raise ValueError('Manifest incompleto')
        zip_url=m['zip_url'];checksum=m['sha256'];ver=m['version']
        if not isinstance(zip_url,str) or not zip_url.startswith('https://') or not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum.lower()):raise ValueError('Manifest non valido')
        if not isinstance(ver,str) or not ver or len(ver)>32:raise ValueError('Versione non valida')
        return {'configured':True,'version':VERSION,'available_version':ver,'update_available':ver!=VERSION,'zip_url':zip_url,'sha256':checksum,'note':'Download automatico in area temporanea, installazione solo su conferma.'}
    except Exception as e:return {'configured':True,'version':VERSION,'error':str(e)[:200]}
