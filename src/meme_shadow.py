"""NEXUS 3.9: evidence-based shadow signals, NOT simulated orders.

Every signal is a rules-only hypothetical observation at a scanner timestamp.
A result is published only when a later real REST quote is observed at or
after the target time, and within a bounded grace period. There are no fills,
no invented prices, no wallet writes, no execution authorizations and no paid
model calls. This is NOT a profit backtest or verified tradeability.
"""
import math
import time
from meme_scout import ADDRESS

HORIZON_SECONDS=300
GRACE_SECONDS=300
MAX_NEW_PER_SCAN=3
MAX_PENDING=20
COOLDOWN_SECONDS=1800
MAX_HISTORY=350
KEEP_SECONDS=7*86400
BUY_FEE=0.03
SELL_FEE=0.03

def _num(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>=0 else None
    except (TypeError,ValueError,OverflowError):return None

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS meme_shadow_signals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT NOT NULL,symbol TEXT NOT NULL,
        created_at INTEGER NOT NULL,target_at INTEGER NOT NULL,
        entry_price_usd REAL NOT NULL,score INTEGER NOT NULL,
        rationale TEXT NOT NULL,liquidity_usd REAL NOT NULL,
        volume_24h_usd REAL NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',
        evaluated_at INTEGER,exit_price_usd REAL,gross_change_pct REAL,
        modeled_net_change_pct REAL,exit_note TEXT NOT NULL DEFAULT '')""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_meme_shadow_pending
        ON meme_shadow_signals(status,target_at)""")

def score_candidate(row):
    """Deterministic quality score; unknown age never presented as verified."""
    if not isinstance(row,dict):return None
    address=row.get('address')
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):return None
    p=_num(row.get('price_usd'))
    liq=_num(row.get('liquidity_usd'))
    vol=_num(row.get('volume_24h_usd'))
    age=_num(row.get('pool_age_hours'))
    if not p or liq is None or vol is None:return None
    if liq<10000 or vol<20000:return None
    if age is not None and age<0.5:return None
    score=50
    score+=min(20,int(liq//10000)*4)
    score+=min(20,int(vol//20000)*4)
    if age is not None:score+=10 if age>=1 else 5
    rationale=('LIQ '+str(round(liq))+' USD · VOL24H '+str(round(vol))+
               ' USD · POOL '+(format(age,'.2f')+'h' if age is not None else
               'ETA NON VERIFICATA')+' · SCORING LOCALE')
    return {'address':address,'symbol':str(row.get('symbol') or '?')[:24],
            'price':p,'liquidity':liq,'volume':vol,'score':score,
            'rationale':rationale}

def capture(c,rows,now=None,source='SCANNER'):
    """Create bounded shadow candidates only on genuine scanner observations.

    The scoring decision is NOT a paper BUY and can never alter user funds.
    """
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    if not isinstance(rows,list):return 0
    accepted=[]
    seen=set()
    for row in rows[:30]:
        candidate=score_candidate(row)
        if candidate is None or candidate['address'] in seen:continue
        seen.add(candidate['address'])
        accepted.append(candidate)
    accepted.sort(key=lambda x:(-x['score'],-x['liquidity'],x['address']))
    pending=c.execute("""SELECT COUNT(*) FROM meme_shadow_signals
        WHERE status='PENDING'""").fetchone()[0]
    added=0
    for d in accepted:
        if pending>=MAX_PENDING or added>=MAX_NEW_PER_SCAN:break
        prior=c.execute("""SELECT MAX(created_at) FROM meme_shadow_signals
            WHERE address=?""",(d['address'],)).fetchone()[0]
        if prior is not None and now-int(prior)<COOLDOWN_SECONDS:continue
        c.execute("""INSERT INTO meme_shadow_signals(
            address,symbol,created_at,target_at,entry_price_usd,score,
            rationale,liquidity_usd,volume_24h_usd,status)
            VALUES(?,?,?,?,?,?,?,?,?,'PENDING')""",
            (d['address'],d['symbol'],now,now+HORIZON_SECONDS,d['price'],
             d['score'],d['rationale'],d['liquidity'],d['volume']))
        added+=1
        pending+=1
    c.execute("DELETE FROM meme_shadow_signals WHERE created_at<? AND status!='PENDING'",
              (now-KEEP_SECONDS,))
    c.execute("""DELETE FROM meme_shadow_signals WHERE status!='PENDING'
        AND id NOT IN (SELECT id FROM meme_shadow_signals
        WHERE status!='PENDING' ORDER BY id DESC LIMIT ?)""",(MAX_HISTORY,))
    return added

def evaluate(c,now=None):
    """Resolve signals against actual after-target REST observations only.

    Missing future quotes remain INSUFFICIENT_DATA. If data starts only after
    the grace window, the signal is marked EXPIRED, never a synthetic trade.
    """
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    settled=0
    expired=0
    pending=c.execute("""SELECT * FROM meme_shadow_signals
        WHERE status='PENDING' AND target_at<=? ORDER BY target_at,id LIMIT 80""",
        (now,)).fetchall()
    for row in pending:
        target=int(row['target_at'])
        observation=c.execute("""SELECT observed_at,price_usd
            FROM meme_quote_reads WHERE address=?
              AND observed_at>=? AND observed_at<=?
            ORDER BY observed_at,id LIMIT 1""",
            (row['address'],target,target+GRACE_SECONDS)).fetchone()
        if observation is not None:
            price=_num(observation['price_usd'])
            entry=_num(row['entry_price_usd'])
            if price and entry:
                gross=price/entry-1
                modeled_net=(price*(1-SELL_FEE)/(entry*(1+BUY_FEE)))-1
                c.execute("""UPDATE meme_shadow_signals
                    SET status='OBSERVED',evaluated_at=?,exit_price_usd=?,
                        gross_change_pct=?,modeled_net_change_pct=?,
                        exit_note='POST_TARGET_REST_OBSERVATION_NO_FILL'
                    WHERE id=? AND status='PENDING'""",
                    (int(observation['observed_at']),price,round(gross*100,4),
                     round(modeled_net*100,4),row['id']))
                settled+=1
                continue
        if now>target+GRACE_SECONDS:
            c.execute("""UPDATE meme_shadow_signals SET status='INSUFFICIENT_DATA',
                evaluated_at=?,exit_note='NO_FRESH_QUOTE_IN_TARGET_WINDOW'
                WHERE id=? AND status='PENDING'""",(now,row['id']))
            expired+=1
    return {'observed':settled,'insufficient_data':expired}

def report(c,now=None):
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    rows=[dict(x) for x in c.execute("""SELECT * FROM meme_shadow_signals
        ORDER BY id DESC LIMIT 45""")]
    totals={x['status']:x['n'] for x in c.execute("""SELECT status,COUNT(*) n
        FROM meme_shadow_signals GROUP BY status""")}
    observed=[x for x in rows if x['status']=='OBSERVED']
    # Descriptive conditional statistics ONLY; no suggestion of executable P/L.
    positive=sum((x['modeled_net_change_pct'] or 0)>0 for x in observed)
    return {'mode':'SHADOW_OBSERVATION_ONLY','horizon_seconds':HORIZON_SECONDS,
            'grace_seconds':GRACE_SECONDS,
            'pending':totals.get('PENDING',0),'observed':totals.get('OBSERVED',0),
            'insufficient_data':totals.get('INSUFFICIENT_DATA',0),
            'recent_observed_count':len(observed),
            'recent_positive_after_modeled_fees':positive,
            'recent_positive_ratio_pct':round(100*positive/len(observed),2) if observed else None,
            'signals':rows,
            'disclaimer':('Segnali teorici basati su scan e quote REST osservate. '
                'Nessun ordine, nessun fill, nessuna verifica della vendibilita, '
                'nessuna garanzia che un trade sarebbe stato possibile. '
                'La variazione netta e un modello con 3% per lato, non un rendimento. '
                'Casi senza quotazioni nell intervallo: DATI INSUFFICIENTI.')}
