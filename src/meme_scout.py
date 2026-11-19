"""NEXUS MEME SCOUT: manual, read-only Solana research. NO MEME EXECUTION.

DEX Screener latest profiles are a DISCOVERY SAMPLE, not all new coins.
All safety-sensitive fields are unverified. Never return a BUY authorization.
"""
import json
import math
import re
import time
from urllib.request import Request, urlopen

PROFILES='https://api.dexscreener.com/token-profiles/latest/v1'
PAIRS_ROOT='https://api.dexscreener.com/tokens/v1/solana/'
ADDRESS=re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
MAX_TOKENS=30
MAX_RESULTS=30


def _get_json(url):
    req=Request(url,headers={'User-Agent':'NEXUS-Research-Only/2.7','Accept':'application/json'})
    with urlopen(req,timeout=7) as response:
        if response.status!=200:
            raise ValueError('Fonte HTTP non disponibile')
        body=response.read(450001)
    if len(body)>450000:
        raise ValueError('Risposta fonte troppo grande')
    return json.loads(body)


def _number(value):
    try: n=float(value)
    except (ValueError,TypeError,OverflowError):return None
    return n if math.isfinite(n) and n>=0 else None


def analyze(profiles,pairs,now_ms=None):
    """Pure evaluator; unsupported/missing liquidity is never an approval."""
    now_ms=int(time.time()*1000) if now_ms is None else int(now_ms)
    if not isinstance(profiles,list) or not isinstance(pairs,list):
        raise ValueError('Risposta Dex Screener malformata')
    addresses=[]
    for p in profiles[:250]:
        if not isinstance(p,dict) or p.get('chainId')!='solana':continue
        a=p.get('tokenAddress')
        if isinstance(a,str) and ADDRESS.fullmatch(a) and a not in addresses:
            addresses.append(a)
        if len(addresses)>=MAX_TOKENS:break
    mapping={}
    for pair in pairs[:300]:
        if not isinstance(pair,dict) or pair.get('chainId')!='solana':continue
        base=pair.get('baseToken') or {}
        quote=pair.get('quoteToken') or {}
        if not isinstance(base,dict) or not isinstance(quote,dict):continue
        address=base.get('address')
        if address not in addresses:continue
        liq=_number((pair.get('liquidity') or {}).get('usd')) if isinstance(pair.get('liquidity'),dict) else None
        previous=mapping.get(address)
        previous_liq=_number((previous.get('liquidity') or {}).get('usd')) if previous else None
        if previous is None or (liq if liq is not None else -1)>(previous_liq if previous_liq is not None else -1):
            mapping[address]=pair
    rows=[]
    for address in addresses:
        pair=mapping.get(address)
        if pair is None:continue
        liq=_number((pair.get('liquidity') or {}).get('usd')) if isinstance(pair.get('liquidity'),dict) else None
        volumes=pair.get('volume') or {}
        vol=_number(volumes.get('h24')) if isinstance(volumes,dict) else None
        tx=pair.get('txns') or {}
        h24=tx.get('h24') or {} if isinstance(tx,dict) else {}
        buys=_number(h24.get('buys')) if isinstance(h24,dict) else None
        sells=_number(h24.get('sells')) if isinstance(h24,dict) else None
        created=_number(pair.get('pairCreatedAt'))
        age_hours=(now_ms-created)/3600000 if created is not None and created<=now_ms else None
        price=_number(pair.get('priceUsd'))
        flags=[]
        if liq is None:flags.append('Liquidità non verificabile')
        elif liq<10000:flags.append('Liquidità osservata sotto $10k')
        if vol is None:flags.append('Volume 24h non disponibile')
        if age_hours is None:flags.append('Età pool non verificabile')
        elif age_hours<24:flags.append('Pool creato da meno di 24h')
        if buys is None or sells is None:flags.append('Conteggio transazioni incompleto')
        if price is None or price==0:flags.append('Prezzo USD non disponibile')
        # No risk score, buy signal, or token contract audit is inferred.
        base=pair.get('baseToken') or {}
        url=pair.get('url')
        if not isinstance(url,str) or not url.startswith('https://dexscreener.com/solana/'):
            url=None
        rows.append({'address':address,
                     'symbol':str(base.get('symbol') or '?')[:30],
                     'name':str(base.get('name') or '?')[:70],
                     'dex':str(pair.get('dexId') or '?')[:40],
                     'price_usd':price,'liquidity_usd':liq,'volume_24h_usd':vol,
                     'txns_24h':None if buys is None or sells is None else int(buys+sells),
                     'pool_age_hours':round(age_hours,2) if age_hours is not None else None,
                     'warnings':flags,
                     'security':'NON_VERIFICATA',
                     'trade_authorized':False,'url':url})
    rows.sort(key=lambda p: (p['liquidity_usd'] is None,-(p['liquidity_usd'] or 0)))
    return {'ok':True,'mode':'READ_ONLY','chain':'solana',
            'source':'DEX Screener public REST latest token profiles + pairs',
            'observed_at':now_ms//1000,'sampled_profiles':len(addresses),
            'candidates':rows[:MAX_RESULTS],
            'warning':'Profili recenti non equivalgono a tutte le nuove memecoin. Nessuna verifica on-chain su mint/freeze authority, holder, sellability, honeypot o liquidità bloccata. TUTTI i candidati sono NON VERIFICATI e non acquistabili.',
            'meme_execution':'BLOCKED'}


def scan(fetch=_get_json):
    profiles=fetch(PROFILES)
    if not isinstance(profiles,list):raise ValueError('Profili non validi')
    addresses=[]
    for item in profiles[:250]:
        if isinstance(item,dict) and item.get('chainId')=='solana':
            a=item.get('tokenAddress')
            if isinstance(a,str) and ADDRESS.fullmatch(a) and a not in addresses:
                addresses.append(a)
                if len(addresses)>=MAX_TOKENS:break
    pairs=fetch(PAIRS_ROOT+','.join(addresses)) if addresses else []
    return analyze(profiles,pairs)
