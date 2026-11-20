"""NEXUS 4.3: evaluation of AI Shadow hypotheses against real REST observations.

Research metrics only. Every baseline is frozen at model completion; never
backfill a reference using future knowledge. Each horizon uses the FIRST real
REST read in a short post-target window. Missing data is explicitly missing.
No AI network calls, trade execution, account edits, or risk-lock changes.
"""
import math
import time

HORIZONS=(300,900,1800)
MAX_BASELINE_AGE=45
MAX_FOLLOWUP_DELAY=120

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS v4_ai_outcome_checks(
      review_id INTEGER NOT NULL,
      horizon_seconds INTEGER NOT NULL,
      address TEXT NOT NULL,
      symbol TEXT NOT NULL,
      reference_at INTEGER NOT NULL,
      reference_quote_at INTEGER,
      reference_price_usd REAL,
      ai_verdict TEXT NOT NULL,
      python_verdict TEXT NOT NULL,
      target_at INTEGER NOT NULL,
      status TEXT NOT NULL,
      followup_at INTEGER,
      followup_price_usd REAL,
      return_pct REAL,
      PRIMARY KEY(review_id,horizon_seconds))""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_v4_ai_check_status_target
        ON v4_ai_outcome_checks(status,target_at)""")

def _valid_price(value):
    try:
        price=float(value)
        return price if math.isfinite(price) and price>0 else None
    except (TypeError,ValueError,OverflowError):
        return None

def seed(c, request, verdict, now=None):
    """Freeze provider-observation baseline once, immediately after COMPLETED.

    If REST has not refreshed within 45s, no baseline is eligible. Do not
    retrospectively create one after more quotes or a server restart.
    """
    from meme_prices import initialize as init_prices
    initialize(c)
    init_prices(c)
    now=int(time.time()) if now is None else int(now)
    record=c.execute("""SELECT timestamp,address,symbol,outcome,verdict
        FROM v4_ai_shadow_audit WHERE id=?""",(request['audit_id'],)).fetchone()
    if not record or record['outcome']!='COMPLETED':
        return False
    existing=c.execute("""SELECT 1 FROM v4_ai_outcome_checks
        WHERE review_id=? LIMIT 1""",(request['audit_id'],)).fetchone()
    if existing:return False
    # Use the timestamp of model completion rather than the earlier prompt.
    q=c.execute("""SELECT observed_at,price_usd FROM meme_quote_reads
      WHERE address=? AND source='DEX_SCREENER_REST' AND observed_at<=?
      ORDER BY observed_at DESC,id DESC LIMIT 1""",(record['address'],now)).fetchone()
    reference_price=_valid_price(q['price_usd']) if q else None
    reference_at=int(q['observed_at']) if q else None
    if (reference_at is None or now-reference_at>MAX_BASELINE_AGE):
        reference_at=None;reference_price=None
    for seconds in HORIZONS:
        c.execute("""INSERT OR IGNORE INTO v4_ai_outcome_checks
          (review_id,horizon_seconds,address,symbol,reference_at,
           reference_quote_at,reference_price_usd,ai_verdict,
           python_verdict,target_at,status)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
              request['audit_id'],seconds,record['address'],record['symbol'],
              now,reference_at,reference_price,
              record['verdict'],str(request.get('rules_verdict') or 'UNKNOWN')[:16],
              now+seconds,'PENDING' if reference_price else 'NO_BASELINE'))
    return True

def evaluate(c, now=None):
    """Settle due windows using FIRST genuine subsequent provider read.

    A delayed worker may settle an older horizon only when historical reads
    provide an on-time observation; no extrapolation or carry-forward.
    """
    from meme_prices import initialize as init_prices
    initialize(c)
    init_prices(c)
    now=int(time.time()) if now is None else int(now)
    records=c.execute("""SELECT review_id,horizon_seconds,address,target_at,
        reference_price_usd FROM v4_ai_outcome_checks
        WHERE status='PENDING' AND target_at<=? ORDER BY target_at LIMIT 120""",
        (now,)).fetchall()
    updated=0
    for r in records:
        target=int(r['target_at'])
        followup=c.execute("""SELECT observed_at,price_usd
            FROM meme_quote_reads WHERE address=? AND source='DEX_SCREENER_REST'
              AND observed_at>=? AND observed_at<=?
            ORDER BY observed_at ASC,id ASC LIMIT 1""",
            (r['address'],target,target+MAX_FOLLOWUP_DELAY)).fetchone()
        p=_valid_price(followup['price_usd']) if followup else None
        if p is not None:
            ret=(p/float(r['reference_price_usd'])-1)*100
            c.execute("""UPDATE v4_ai_outcome_checks SET status='OBSERVED',
                followup_at=?,followup_price_usd=?,return_pct=?
                WHERE review_id=? AND horizon_seconds=? AND status='PENDING'""",
                (followup['observed_at'],p,round(ret,6),r['review_id'],
                 r['horizon_seconds']))
            updated+=1
        elif now>target+MAX_FOLLOWUP_DELAY:
            c.execute("""UPDATE v4_ai_outcome_checks SET status='MISSING_QUOTE'
                WHERE review_id=? AND horizon_seconds=? AND status='PENDING'""",
                (r['review_id'],r['horizon_seconds']))
            updated+=1
    return updated

def report(c):
    initialize(c)
    rows=[dict(row) for row in c.execute("""SELECT review_id,horizon_seconds,
      address,symbol,reference_at,reference_quote_at,reference_price_usd,
      ai_verdict,python_verdict,target_at,status,followup_at,
      followup_price_usd,return_pct FROM v4_ai_outcome_checks
      ORDER BY review_id DESC,horizon_seconds ASC LIMIT 90""")]
    for r in rows:
        r['comparison'] = ('AGREE' if r['ai_verdict']==r['python_verdict'] else
                           'DIFFER' if r['python_verdict'] in ('BUY','SELL','WAIT') else
                           'UNKNOWN')
    # Counts are per review, not repeated three times over three horizons.
    single=[r for r in rows if r['horizon_seconds']==300]
    stats={'evaluated_reviews':len(single),
           'rule_agreements':sum(r['comparison']=='AGREE' for r in single),
           'rule_disagreements':sum(r['comparison']=='DIFFER' for r in single),
           'legacy_no_reference':c.execute("""SELECT COUNT(*) FROM v4_ai_shadow_audit a
             WHERE a.outcome='COMPLETED' AND NOT EXISTS
             (SELECT 1 FROM v4_ai_outcome_checks b WHERE b.review_id=a.id)""").fetchone()[0]}
    horizons=[]
    for seconds in HORIZONS:
        subset=[r for r in rows if r['horizon_seconds']==seconds]
        observed=[r for r in subset if r['status']=='OBSERVED']
        # WAIT is neither a correct nor incorrect directional prediction.
        wait=[r for r in observed if r['ai_verdict']=='WAIT']
        directional=[r for r in observed if r['ai_verdict'] in ('BUY','SELL')]
        correct=sum((r['ai_verdict']=='BUY' and r['return_pct']>0)
                    or (r['ai_verdict']=='SELL' and r['return_pct']<0)
                    for r in directional)
        horizons.append({'seconds':seconds,'total':len(subset),
            'pending':sum(r['status']=='PENDING' for r in subset),
            'observed':len(observed),
            'missing':sum(r['status']=='MISSING_QUOTE' for r in subset),
            'no_baseline':sum(r['status']=='NO_BASELINE' for r in subset),
            'wait_observed':len(wait),
            'wait_declines':sum(r['return_pct']<0 for r in wait),
            'wait_rises':sum(r['return_pct']>0 for r in wait),
            'directional_observed':len(directional),
            'directional_correct':correct,
            'mean_return_pct':(round(sum(r['return_pct'] for r in observed)/len(observed),4)
                               if observed else None)})
    return {'mode':'AI_SHADOW_OUTCOME_OBSERVATION','horizons_seconds':list(HORIZONS),
        'source':'DEX_SCREENER_REST_READS','max_followup_delay_seconds':MAX_FOLLOWUP_DELAY,
        'metrics_are_not_trading_performance':True,
        'note':('Confronto descrittivo, NON profitti o accuratezza predittiva certificata. '
                'WAIT non e una previsione direzionale. Prezzi REST non eseguibili; '
                'dati mancanti esclusi dai calcoli. La decisione Python e '
                'quella alla selezione del candidato, non un ordine.'),
        'stats':stats,'horizons':horizons,'checks':rows}
