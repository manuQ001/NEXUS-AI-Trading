"""Isolated audit of manually requested AI comments against later closed candles.

Research measurements are NOT trade decisions, AI prediction accuracy,
execution prices or profit. No credentials or private account data are stored.
"""
import json
import math
import time
from hypothesis import validate_hypotheses, check_hypothesis, NEUTRAL_BPS

HORIZONS=(3,12)  # 15 and 60 minutes on uninterrupted 5-minute candles


def init(c):
    c.execute('''CREATE TABLE IF NOT EXISTS ai_research (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        base_candle_time INTEGER NOT NULL,
        base_close REAL NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        proposal TEXT NOT NULL,
        risk_veto INTEGER NOT NULL,
        analysis_json TEXT NOT NULL,
        UNIQUE(symbol,base_candle_time,provider,model)
    )''')
    # Forward-compatible schema migration. Existing consults remain unscored.
    cols={row[1] for row in c.execute('PRAGMA table_info(ai_research)').fetchall()}
    if 'hypotheses_json' not in cols:
        c.execute('ALTER TABLE ai_research ADD COLUMN hypotheses_json TEXT')
    c.execute('''CREATE TABLE IF NOT EXISTS ai_research_outcomes (
        research_id INTEGER NOT NULL,
        horizon_bars INTEGER NOT NULL,
        status TEXT NOT NULL,
        target_candle_time INTEGER NOT NULL,
        close_eur REAL,
        price_change_bps REAL,
        PRIMARY KEY(research_id,horizon_bars),
        FOREIGN KEY(research_id) REFERENCES ai_research(id)
    )''')


def record(c, report, advice, *, now=None):
    """Store a fresh, successful advisory snapshot; never accept stale candles."""
    now=int(time.time()) if now is None else int(now)
    if not isinstance(report,dict) or not isinstance(advice,dict) or not advice.get('available'):
        return {'saved':False,'reason':'NO_VALID_ADVICE'}
    if advice.get('status')!='advisory_only':
        return {'saved':False,'reason':'NO_VALID_ADVICE'}
    symbol=report.get('symbol')
    if symbol not in ('BTC','ETH'):
        return {'saved':False,'reason':'INVALID_SYMBOL'}
    try:
        base=int(report['time'])
        close=float(report['reference_close'])
    except (KeyError,TypeError,ValueError,OverflowError):
        return {'saved':False,'reason':'MISSING_REFERENCE'}
    if not math.isfinite(close) or close<=0 or base<=0:
        return {'saved':False,'reason':'INVALID_REFERENCE'}
    # The candle timestamp is its start, never its close. Avoid backdated
    # "advice" if its reference was not yet closed or has gone stale.
    if not base+300<=now<=base+600:
        return {'saved':False,'reason':'STALE_CANDLE'}
    model=advice.get('model','')
    provider=advice.get('provider','Ollama')
    analysis=advice.get('analysis')
    if not isinstance(provider,str) or provider not in ('OpenAI','Ollama'):
        return {'saved':False,'reason':'INVALID_PROVIDER'}
    if not isinstance(model,str) or not 1<=len(model)<=80:
        return {'saved':False,'reason':'INVALID_MODEL'}
    if not isinstance(analysis,dict) or not analysis or not all(
            isinstance(k,str) and isinstance(v,str) and 0<len(v)<=800
            for k,v in analysis.items()):
        return {'saved':False,'reason':'INVALID_ANALYSIS'}
    safe=json.dumps(analysis,ensure_ascii=False)
    if len(safe)>4000:
        return {'saved':False,'reason':'INVALID_ANALYSIS'}
    # Local Ollama currently provides prose only; do not synthesize predictions.
    hypotheses=advice.get('hypotheses')
    if hypotheses is not None:
        try:
            hypotheses=validate_hypotheses(hypotheses)
        except ValueError:
            return {'saved':False,'reason':'INVALID_HYPOTHESES'}
    init(c)
    cursor=c.execute('''INSERT OR IGNORE INTO ai_research
        (created_at,symbol,base_candle_time,base_close,provider,model,proposal,risk_veto,analysis_json,hypotheses_json)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (now,symbol,base,close,provider,model,str(report.get('proposal','WAIT'))[:20],
         int(report.get('risk_veto') is True),safe,
         json.dumps(hypotheses,ensure_ascii=False) if hypotheses is not None else None))
    return {'saved':cursor.rowcount==1,
            'reason':'SAVED' if cursor.rowcount==1 else 'DUPLICATE_SNAPSHOT'}


def update_outcomes(c, symbol, candles, *, now=None):
    """Attach later completed closes only, requiring uninterrupted candle slots.

    Outcomes are raw price changes in basis points, not signed predictions
    or realized P/L. Missing bars are labelled DATA_GAP, never interpolated.
    """
    if symbol not in ('BTC','ETH'):
        raise ValueError('Simbolo non supportato')
    now=int(time.time()) if now is None else int(now)
    init(c)
    series={}
    for candle in candles:
        try:
            t=int(candle['time']);p=float(candle['close'])
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
        if t>0 and math.isfinite(p) and p>0 and t+300<=now:
            series[t]=p
    if not series:return 0
    latest=max(series)
    rows=c.execute('''SELECT a.id,a.base_candle_time,a.base_close,a.created_at
        FROM ai_research a WHERE a.symbol=? AND EXISTS (
        SELECT 1 FROM (SELECT 3 AS horizon UNION ALL SELECT 12) h
        WHERE NOT EXISTS (SELECT 1 FROM ai_research_outcomes o
            WHERE o.research_id=a.id AND o.horizon_bars=h.horizon))
        ORDER BY a.id DESC LIMIT 500''',(symbol,)).fetchall()
    count=0
    for row in rows:
        base=row['base_candle_time']
        for horizon in HORIZONS:
            target=base+horizon*300
            if target+300>now or latest<target:continue
            if c.execute('SELECT 1 FROM ai_research_outcomes WHERE research_id=? AND horizon_bars=?',
                         (row['id'],horizon)).fetchone():
                continue
            # Treat irregular timestamps and holes as missing evidence.
            full=all(base+i*300 in series for i in range(1,horizon+1))
            status='OBSERVED' if full and row['created_at']<target+300 else 'DATA_GAP'
            price=series[target] if status=='OBSERVED' else None
            delta=round((price/row['base_close']-1)*10000,3) if price is not None else None
            c.execute('''INSERT OR IGNORE INTO ai_research_outcomes
                (research_id,horizon_bars,status,target_candle_time,close_eur,price_change_bps)
                VALUES(?,?,?,?,?,?)''',(row['id'],horizon,status,target,price,delta))
            count+=1
    return count


def latest(c, *, limit=20):
    """Read-only audit report, never performance or signal scoring."""
    if not 1<=limit<=100:raise ValueError('Limite non valido')
    init(c)
    rows=c.execute('''SELECT id,created_at,symbol,base_candle_time,base_close,
        provider,model,proposal,risk_veto,analysis_json,hypotheses_json
        FROM ai_research ORDER BY id DESC LIMIT ?''',(limit,)).fetchall()
    entries=[]
    for row in rows:
        outcomes=[dict(o) for o in c.execute('''SELECT horizon_bars,status,
            target_candle_time,close_eur,price_change_bps
            FROM ai_research_outcomes WHERE research_id=? ORDER BY horizon_bars''',
            (row['id'],))]
        item={k:row[k] for k in ('id','created_at','symbol','base_candle_time',
              'base_close','provider','model','proposal','risk_veto')}
        item['analysis']=json.loads(row['analysis_json'])
        item['outcomes']=outcomes
        hypotheses=(json.loads(row['hypotheses_json'])
                    if row['hypotheses_json'] else None)
        if hypotheses is not None:
            item['hypotheses']=[]
            for hypothesis in validate_hypotheses(hypotheses):
                outcome=next((x for x in outcomes
                              if x['horizon_bars']==hypothesis['horizon_bars']),None)
                assessment=check_hypothesis(hypothesis['direction'],
                    outcome['status'] if outcome else None,
                    outcome['price_change_bps'] if outcome else None)
                item['hypotheses'].append({**hypothesis,'assessment':assessment})
        else:
            item['hypotheses']=None
        entries.append(item)
    return {'entries':entries,'mode':'RESEARCH ONLY / NO TRADE SCORING',
            'horizons_bars':list(HORIZONS),'neutral_band_bps':NEUTRAL_BPS,
            'note':'Confronto direzionale descrittivo con fascia neutra fissa ±10 bps; NON profitto, win rate operativo o prova di capacità predittiva. Intervalli incompleti: DATA_GAP.'}
