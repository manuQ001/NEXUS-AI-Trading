"""RUG GUARD 2.0 — optional GoPlus Solana analysis, advisory-only.

No token passes into an execution path; missing data / service failure -> UNKNOWN.
GoPlus API schema is a third-party source, not proof of safety or sellability.
"""
import json
import os
import re
import time
from urllib.request import Request,urlopen
from urllib.parse import urlencode

ADDRESS=re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
API='https://api.gopluslabs.io/api/v1/solana/token_security'
MAX_BYTES=350000

def _status(obj):
    """Parse explicitly reported 0/1; booleans and undocumented shapes are unknown."""
    if isinstance(obj,dict):obj=obj.get('status')
    if obj is True or obj==1 or obj=='1':return 'PRESENTE'
    if obj is False or (type(obj) is int and obj==0) or obj=='0':return 'ASSENTE'
    return 'NON_DISPONIBILE'

def _fetch(address):
    url=API+'?'+urlencode({'contract_addresses':address})
    headers={'User-Agent':'NEXUS-Research-Only/2.7','Accept':'application/json'}
    token=os.environ.get('NEXUS_GOPLUS_API_TOKEN','').strip()
    if token and ('\n' in token or '\r' in token or len(token)>4096):
        raise ValueError('Token GoPlus non valido')
    if token:headers['Authorization']='Bearer '+token
    with urlopen(Request(url,headers=headers),timeout=8) as response:
        if response.status!=200:raise ValueError('Risposta GoPlus non valida')
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Risposta GoPlus troppo grande')
    return json.loads(raw)

def analyze(address,payload,now=None):
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):
        raise ValueError('Mint Solana non valido')
    if not isinstance(payload,dict) or str(payload.get('code'))!='1':
        raise ValueError('GoPlus non ha confermato la risposta')
    result=payload.get('result')
    if not isinstance(result,dict):raise ValueError('Risultato GoPlus mancante')
    item=result.get(address)
    if not isinstance(item,dict):
        # Some APIs normalize address case: Solana is case-sensitive, so do not
        # auto-match another key or assert a risk result for the wrong mint.
        raise ValueError('Token richiesto non presente nella risposta')
    names=[('mintable','Autorità mint'),('freezable','Autorità freeze'),
           ('close_authority','Autorità di chiusura'),('balance_mutable','Modifica saldi'),
           ('metadata_mutable','Metadati modificabili'),('transfer_hook','Transfer hook'),
           ('non_transferable','Non trasferibile')]
    checks=[]
    findings=[]
    missing=[]
    for field,label in names:
        observed=_status(item.get(field))
        checks.append({'field':field,'label':label,'status':observed})
        if observed=='PRESENTE':findings.append(label)
        if observed=='NON_DISPONIBILE':missing.append(label)
    holders=item.get('holders')
    if not isinstance(holders,list):holders=[]
    percentages=[]
    for h in holders[:10]:
        if not isinstance(h,dict):continue
        try:
            n=float(h.get('percent'))
            if not 0<=n<=1:continue
        except (TypeError,ValueError,OverflowError):continue
        percentages.append(n)
    top10_pct=round(sum(percentages)*100,2) if len(percentages)==10 else None
    if top10_pct is None:missing.append('Concentrazione dei primi 10 holder')
    elif top10_pct>=60:findings.append('Concentrazione primi 10 holder almeno 60%')
    if item.get('trusted_token') in ('1',1,True):
        # Still not an approval signal.
        trusted='SEGNALATO_DA_GOPLUS'
    else:trusted='NON_CONFERMATO'
    return {
        'ok':True,'mode':'READ_ONLY','provider':'GoPlus Solana Token Security (beta)',
        'address':address,'checked_at':int(time.time()) if now is None else int(now),
        'status':'RISCHI_RILEVATI' if findings else 'DATI_INCOMPLETI' if missing else 'NESSUN_FLAG_NEI_CAMPI_LETTI',
        'findings':findings,'missing':missing,'checks':checks,
        'top10_holder_pct':top10_pct,'trusted_token':trusted,
        'sellability':'NON_VERIFICATA','liquidity_lock':'NON_VERIFICATA',
        'trade_authorized':False,'meme_execution':'BLOCKED',
        'warning':'Indicatori riportati da una fonte esterna. Un campo ASSENTE non prova sicurezza. Non viene simulata alcuna vendita; sellability, LP lock e rischio honeypot non sono verificati. Nessun acquisto consentito.'
    }

def inspect(address,fetch=_fetch):
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):
        raise ValueError('Mint Solana non valido')
    return analyze(address,fetch(address))
