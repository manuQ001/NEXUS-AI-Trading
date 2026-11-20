"""NEXUS 3.6 paper desk: decision audit, eight role statuses, live diagnostics.

Never treats missing on-chain or social evidence as verified. No execution,
wallet access, credentials, external orders, or synthetic price histories.
"""
import math
import time
from collections import Counter
from meme_scout import ADDRESS

MAX_ROWS=1000
KEEP_SECONDS=7*86400

def _positive(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>0 else None
    except (ValueError,TypeError,OverflowError):
        return None

def _nonnegative(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>=0 else None
    except (ValueError,TypeError,OverflowError):
        return None

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS meme_scan_decisions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observed_at INTEGER NOT NULL,address TEXT NOT NULL,
        symbol TEXT NOT NULL,source TEXT NOT NULL,
        liquidity_usd REAL,volume_24h_usd REAL,
        price_usd REAL,pool_age_hours REAL,
        decision TEXT NOT NULL,reason TEXT NOT NULL)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_meme_decisions_time
        ON meme_scan_decisions(observed_at)""")

def classify(row,guard_blocked=False):
    """Classify one observed candidate using AUTO entry gates, no network calls."""
    from meme_auto import MIN_ENTRY_LIQUIDITY, MIN_ENTRY_VOLUME, MIN_POOL_AGE_HOURS
    price=_positive(row.get('price_usd'))
    liq=_positive(row.get('liquidity_usd'))
    vol=_positive(row.get('volume_24h_usd'))
    age=row.get('pool_age_hours')
    try:
        age=float(age) if age is not None else None
        if age is not None and (not math.isfinite(age) or age<0):age=None
    except (ValueError,TypeError,OverflowError):age=None
    if price is None:return 'REJECTED','PREZZO_NON_VALIDO'
    if liq is None:return 'REJECTED','LIQUIDITA_NON_VERIFICABILE'
    if liq<MIN_ENTRY_LIQUIDITY:return 'REJECTED','LIQUIDITA_BASSA'
    if vol is None:return 'REJECTED','VOLUME_NON_VERIFICABILE'
    if vol<MIN_ENTRY_VOLUME:return 'REJECTED','VOLUME_BASSO'
    if age is not None and age<MIN_POOL_AGE_HOURS:return 'REJECTED','POOL_TROPPO_RECENTE'
    if guard_blocked:return 'WATCH_ONLY','CIRCUIT_BREAKER'
    return 'SCREENED','REQUIRES_QUOTE_RISK_AGENT_AND_CAPITAL_CHECK'

def record_scan(c,rows,now=None,guard_blocked=False,source='SCANNER'):
    """Log decisions for max 30 real observed profiles, never fake trades."""
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    if not isinstance(rows,list):rows=[]
    seen=set()
    counts=Counter()
    for row in rows[:30]:
        if not isinstance(row,dict):continue
        address=row.get('address')
        if not isinstance(address,str) or not ADDRESS.fullmatch(address) or address in seen:
            continue
        seen.add(address)
        decision,reason=classify(row,guard_blocked)
        counts[decision]+=1
        c.execute("""INSERT INTO meme_scan_decisions(
            observed_at,address,symbol,source,liquidity_usd,
            volume_24h_usd,price_usd,pool_age_hours,decision,reason)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",(
            now,address,str(row.get('symbol') or '?')[:24],source[:30],
            _positive(row.get('liquidity_usd')),
            _positive(row.get('volume_24h_usd')),
            _positive(row.get('price_usd')),
            _nonnegative(row.get('pool_age_hours')),decision,reason))
    c.execute('DELETE FROM meme_scan_decisions WHERE observed_at<?',(now-KEEP_SECONDS,))
    c.execute("""DELETE FROM meme_scan_decisions WHERE id NOT IN
        (SELECT id FROM meme_scan_decisions ORDER BY id DESC LIMIT ?)""",(MAX_ROWS,))
    return dict(counts)

def report(c,now=None,stream=None):
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    from meme_auto import circuit_breaker
    guard=circuit_breaker(c,now)
    latest=[dict(x) for x in c.execute("""SELECT observed_at,address,symbol,
        source,liquidity_usd,volume_24h_usd,price_usd,pool_age_hours,
        decision,reason FROM meme_scan_decisions
        ORDER BY id DESC LIMIT 25""")]
    sample=[dict(x) for x in c.execute(
        "SELECT decision,reason FROM meme_scan_decisions ORDER BY id DESC LIMIT 300")]
    reasons=Counter(x['reason'] for x in sample)
    decision_counts=Counter(x['decision'] for x in sample)
    connected=bool(stream and stream.get('connected'))
    recent=bool(stream and stream.get('last_message') and
                0<=now-int(stream['last_message'])<=90)
    # Status describes real connected sources and existing rule workers.
    roles=[
        {'name':'SEARCH','status':'WS_RECENT' if connected and recent else
         ('WS_WAITING' if connected else 'REST_FALLBACK'),'type':'FEED',
         'detail':'DEX Screener profili WebSocket e REST; non tutti i mint Solana'},
        {'name':'RUG','status':'NOT_AUTOMATED','type':'RESEARCH',
         'detail':'Controllo on-chain solo su richiesta; non sorveglia LP o wallet di continuo'},
        {'name':'SNIPER','status':'BLOCKED_BY_RISK' if guard['blocked'] else 'PAPER_READY',
         'type':'EXECUTOR','detail':'BUY solo virtuali, mai swap firmati'},
        {'name':'RISK','status':'CIRCUIT_ACTIVE' if guard['blocked'] else 'LOCAL_RULES',
         'type':'RULE_ENGINE','detail':'Filtri locali; sicurezza e vendibilita non verificate'},
        {'name':'WHALE','status':'NOT_AUTOMATED','type':'RESEARCH',
         'detail':'Analisi RPC su richiesta; nessuna sorveglianza continua smart money'},
        {'name':'EXIT','status':'PAPER_ACTIVE','type':'RULE_ENGINE',
         'detail':'Regole stop, trailing, target e timeout con quote indicative REST'},
        {'name':'SHILL','status':'NOT_CONNECTED','type':'RESEARCH',
         'detail':'Fonti Telegram e social non collegate'},
        {'name':'HEAD OF DESK','status':'LOCAL_COORDINATOR','type':'COORDINATOR',
         'detail':'Orchestra scanner, regole e registro; non e un agente cloud indipendente'}
    ]
    return {'mode':'PAPER_DESK_TELEMETRY_ONLY','time':now,
            'risk':guard,'stream':{'connected':connected,'recent':recent},
            'roles':roles,'reviewed_sample':len(sample),
            'decision_counts':dict(decision_counts),
            'top_reasons':[{'reason':reason,'count':count}
                for reason,count in reasons.most_common(8)],
            'latest':latest,
            'disclaimer':'Otto ruoli descrittivi dello stato reale: NON otto agenti LLM indipendenti. '
                         'SCREENED non equivale a BUY autorizzato. '
                         'Le quote REST non sono eseguibili e la vendibilita e non verificata.'}
