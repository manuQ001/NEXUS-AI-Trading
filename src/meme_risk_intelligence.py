"""NEXUS 3.10: inspectable, read-only MEME risk evidence.

Scanner facts are not on-chain checks. Optional third-party GoPlus lookups
require NEXUS_RISK_GOPLUS_ENABLED=1 (disabled by default, no implied API cost
or verification). Never authorize trades or modify the wallet/risk circuit.
"""
import json
import os
import time
from meme_scout import ADDRESS

MAX_RECORDS=350
MAX_AGE=7*86400
PROVIDER_INTERVAL=90
MAX_PROVIDER_TOKEN_CHECKS=120

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS meme_risk_evidence(
        address TEXT PRIMARY KEY,first_seen INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,symbol TEXT NOT NULL,
        liquidity_usd REAL,volume_24h_usd REAL,
        scanner_risk TEXT NOT NULL,provider_status TEXT NOT NULL,
        provider_checked_at INTEGER,provider_json TEXT NOT NULL DEFAULT '{}',
        provider_error TEXT NOT NULL DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS meme_risk_control(
        id INTEGER PRIMARY KEY CHECK(id=1),
        last_external_attempt INTEGER NOT NULL DEFAULT 0,
        external_checks INTEGER NOT NULL DEFAULT 0,
        external_errors INTEGER NOT NULL DEFAULT 0)""")
    c.execute('INSERT OR IGNORE INTO meme_risk_control(id) VALUES(1)')

def _scanner_state(row):
    try:
        liq=float(row.get('liquidity_usd'))
        vol=float(row.get('volume_24h_usd'))
        if not (liq>=0 and liq<float('inf') and vol>=0 and vol<float('inf')):
            raise ValueError()
    except (ValueError,TypeError,OverflowError):
        return 'INCOMPLETE'
    if liq<10000 or vol<20000:
        return 'LOW_LIQUIDITY_OR_VOLUME'
    return 'FILTERS_PASSED_NOT_SECURITY_VERIFIED'

def record_candidates(c,rows,now=None):
    """Record scanner-observed data; never mark a token as independently safe."""
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    if not isinstance(rows,list):return 0
    added=0
    seen=set()
    for x in rows[:30]:
        if not isinstance(x,dict):continue
        a=x.get('address')
        if not isinstance(a,str) or not ADDRESS.fullmatch(a) or a in seen:continue
        seen.add(a)
        from meme_desk import _positive
        c.execute("""INSERT INTO meme_risk_evidence(
            address,first_seen,last_seen,symbol,liquidity_usd,volume_24h_usd,
            scanner_risk,provider_status) VALUES(?,?,?,?,?,?,?,'NOT_CHECKED')
            ON CONFLICT(address) DO UPDATE SET
            last_seen=excluded.last_seen,symbol=excluded.symbol,
            liquidity_usd=excluded.liquidity_usd,
            volume_24h_usd=excluded.volume_24h_usd,
            scanner_risk=excluded.scanner_risk""",
            (a,now,now,str(x.get('symbol') or '?')[:24],
             _positive(x.get('liquidity_usd')),_positive(x.get('volume_24h_usd')),
             _scanner_state(x)))
        added+=1
    c.execute('DELETE FROM meme_risk_evidence WHERE last_seen<?',(now-MAX_AGE,))
    c.execute("""DELETE FROM meme_risk_evidence WHERE address NOT IN
        (SELECT address FROM meme_risk_evidence ORDER BY last_seen DESC LIMIT ?)""",
        (MAX_RECORDS,))
    return added

def external_enabled(env=None):
    env=os.environ if env is None else env
    return env.get('NEXUS_RISK_GOPLUS_ENABLED')=='1'

def inspect_next(c,now=None,inspect=None,env=None):
    """At most one opted-in GoPlus lookup per 90 sec; safe failure => unknown."""
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    if not external_enabled(env):
        return {'status':'DISABLED','attempted':0}
    last=c.execute('SELECT * FROM meme_risk_control WHERE id=1').fetchone()
    if now-int(last['last_external_attempt'])<PROVIDER_INTERVAL:
        return {'status':'RATE_LIMITED','attempted':0}
    if last['external_checks']>=MAX_PROVIDER_TOKEN_CHECKS:
        return {'status':'BUDGET_LIMIT','attempted':0}
    target=c.execute("""SELECT address FROM meme_risk_evidence WHERE
        provider_checked_at IS NULL AND provider_status='NOT_CHECKED'
        ORDER BY last_seen DESC LIMIT 1""").fetchone()
    if not target:return {'status':'NO_UNCHECKED_TOKEN','attempted':0}
    a=target['address']
    c.execute("""UPDATE meme_risk_control SET last_external_attempt=?,
        external_checks=external_checks+1 WHERE id=1""",(now,))
    from rug_guard import inspect as goplus_inspect
    try:
        result=(inspect or goplus_inspect)(a)
        if not isinstance(result,dict) or result.get('address')!=a or not result.get('ok'):
            raise ValueError('Invalid provider response')
        status=result.get('status')
        if status not in ('RISCHI_RILEVATI','DATI_INCOMPLETI','NESSUN_FLAG_NEI_CAMPI_LETTI'):
            raise ValueError('Invalid provider status')
        evidence={'status':status,'findings':result.get('findings',[])[:15],
                  'missing':result.get('missing',[])[:15],
                  'checks':result.get('checks',[])[:15],
                  'top10_holder_pct':result.get('top10_holder_pct'),
                  'sellability':'NON_VERIFICATA','liquidity_lock':'NON_VERIFICATA'}
        c.execute("""UPDATE meme_risk_evidence SET provider_checked_at=?,
            provider_status=?,provider_json=?,provider_error=''
            WHERE address=?""",(now,status,json.dumps(evidence,ensure_ascii=False),a))
        return {'status':status,'attempted':1,'address':a}
    except (OSError,ValueError,TypeError,KeyError,TimeoutError) as exc:
        c.execute("""UPDATE meme_risk_control SET external_errors=external_errors+1
            WHERE id=1""")
        c.execute("""UPDATE meme_risk_evidence SET provider_status='PROVIDER_ERROR',
            provider_checked_at=?,provider_error=? WHERE address=?""",
            (now,type(exc).__name__,a))
        return {'status':'PROVIDER_ERROR','attempted':1,'address':a}

def report(c,now=None,env=None):
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    control=dict(c.execute('SELECT * FROM meme_risk_control WHERE id=1').fetchone())
    recent=[]
    for x in c.execute("""SELECT * FROM meme_risk_evidence
        ORDER BY last_seen DESC LIMIT 25"""):
        r=dict(x)
        try:evidence=json.loads(r.pop('provider_json'))
        except (TypeError,ValueError):evidence={}
        r['provider_evidence']=evidence
        r['age_seconds']=max(0,now-int(r['last_seen']))
        r['trade_authorized']=False
        recent.append(r)
    counts={r['provider_status']:r['n'] for r in c.execute(
        'SELECT provider_status,COUNT(*) n FROM meme_risk_evidence GROUP BY provider_status')}
    return {'mode':'READ_ONLY_RISK_EVIDENCE',
            'external_goplus_enabled':external_enabled(env),
            'external_checks_used':control['external_checks'],
            'external_check_limit':MAX_PROVIDER_TOKEN_CHECKS,
            'external_errors':control['external_errors'],
            'last_external_attempt':control['last_external_attempt'],
            'total_candidates':c.execute('SELECT COUNT(*) FROM meme_risk_evidence').fetchone()[0],
            'provider_status_counts':counts,'recent':recent,
            'trade_authorized':False,
            'warning':('Scanner volume/liquidita non verificano sicurezza del contratto. '
                 'GoPlus e una fonte esterna opzionale, non prova di assenza di rug. '
                 'Controlli non disponibili restano UNKNOWN. Nessun BUY e sbloccato.')}
