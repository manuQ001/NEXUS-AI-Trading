"""Conservative background download of immutable release ZIPs; never executes downloaded files."""
import hashlib, json, re, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from maintenance import ROOT, VERSION

STAGE=ROOT/'pending_update'
MAX_BYTES=5*1024*1024

def version_tuple(version):
    if not isinstance(version,str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}',version):
        raise ValueError('Versione non valida')
    return tuple(map(int,version.split('.')))

def read_staged():
    meta=STAGE/'release.json'
    if not meta.is_file():return None
    try:
        d=json.loads(meta.read_text('utf-8'))
        z=STAGE/'release.zip'
        if not z.is_file() or not re.fullmatch(r'[0-9a-f]{64}',d['sha256']):return None
        if hashlib.sha256(z.read_bytes()).hexdigest()!=d['sha256']:return None
        if version_tuple(d['version'])<=version_tuple(VERSION):return None
        return {'version':d['version'],'sha256':d['sha256'],'path':str(z)}
    except (KeyError,ValueError,OSError,TypeError):return None

def download_if_available(manifest):
    """Download to staging after validating manifest and SHA-256; never auto-installs."""
    try:
        version=manifest['available_version']
        if version_tuple(version)<=version_tuple(VERSION):return {'downloaded':False,'reason':'Nessuna versione piÃ¹ recente'}
        url=manifest['zip_url'];expected=manifest['sha256'].lower()
        if not isinstance(url,str) or not url.startswith('https://') or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Manifest non valido')
        old=read_staged()
        if old and version_tuple(old['version'])>=version_tuple(version):return {'downloaded':True,'version':old['version'],'cached':True}
        STAGE.mkdir(parents=True,exist_ok=True)
        req=urllib.request.Request(url,headers={'User-Agent':'NEXUS-Paper-Only/2.4'})
        temp=STAGE/'download.part'
        try:
            with urllib.request.urlopen(req,timeout=20) as r, temp.open('wb') as out:
                host=urlsplit(r.geturl()).hostname or ''
                scheme=urlsplit(r.geturl()).scheme
                if scheme!='https' or not (host=='github.com' or host.endswith('.githubusercontent.com')):raise ValueError('Redirect fuori da GitHub')
                digest=hashlib.sha256();received=0
                while True:
                    block=r.read(65536)
                    if not block:break
                    received+=len(block)
                    if received>MAX_BYTES:raise ValueError('Pacchetto troppo grande')
                    digest.update(block);out.write(block)
            if digest.hexdigest()!=expected:raise ValueError('SHA-256 non corrisponde')
            # Downloaded artifact must be a valid NEXUS update package, not arbitrary executable.
            from zipfile import ZipFile
            with ZipFile(temp) as z:
                names=z.namelist()
                if not any(n.endswith('/src/server.py') or n=='src/server.py' for n in names):raise ValueError('ZIP NEXUS non valido')
            temp.replace(STAGE/'release.zip')
            (STAGE/'release.json').write_text(json.dumps({'version':version,'sha256':expected}),encoding='utf-8')
            return {'downloaded':True,'version':version,'note':'Pronto, richiede conferma per installazione'}
        finally:
            temp.unlink(missing_ok=True)
    except Exception as exc:return {'downloaded':False,'error':str(exc)[:250]}
