"""Autonomous MEME PAPER simulation only. No real market orders or wallets.

A single monitor loop processes open positions every 30 seconds and discovers
new candidates every 5 minutes. Buy rules are experimental, not predictions.
Quoted prices are public indicative marks; selling may be impossible in reality.
"""
import math
import time
from meme_demo import initialize, demo_state, quick_trade, indicative_quote, MAX_POSITIONS, STAKE_USD
from meme_scout import scan, ADDRESS

STOP_LOSS=-0.10
TAKE_PROFIT=0.20
MAX_HOLD_SECONDS=2*3600
SCAN_SECONDS=300
COOLDOWN_SECONDS=3600
MIN_AUTO_LIQUIDITY=500.0
MIN_AUTO_VOLUME=500.0
MAX_ENTRIES_PER_SCAN=3


def _number(value):
    try:
        x=float(value)
        return x if math.isfinite(x) and x>=0 else None
    except (ValueError,TypeError,OverflowError):
        return None


def init_auto(c):
    initialize(c)
    c.execute('''CREATE TABLE IF NOT EXISTS meme_auto_state(
        id INTEGER PRIMARY KEY CHECK(id=1),
        enabled INTEGER NOT NULL DEFAULT 1,
        last_scan INTEGER NOT NULL DEFAULT 0,
        last_tick INTEGER NOT NULL DEFAULT 0,
        last_status TEXT NOT NULL DEFAULT 'NON_AVVIATO',
        last_error TEXT NOT NULL DEFAULT '')''')
    c.execute("INSERT OR IGNORE INTO meme_auto_state(id,enabled) VALUES(1,1)")
    c.execute('''CREATE TABLE IF NOT EXISTS meme_auto_journal(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL, address TEXT,
        action TEXT NOT NULL, note TEXT NOT NULL)''')


def status(c):
    init_auto(c)
    a=c.execute('SELECT * FROM meme_auto_state WHERE id=1').fetchone()
    return {'enabled':bool(a['enabled']),'last_scan':a['last_scan'],
            'last_tick':a['last_tick'],'status':a['last_status'],
            'error':a['last_error'],'stop_loss_pct':-10,'take_profit_pct':20,
            'max_hold_minutes':120,'monitor_seconds':30,'scan_seconds':SCAN_SECONDS,
            'mode':'AUTONOMOUS_PAPER_ONLY',
            'journal':[dict(x) for x in c.execute(
                'SELECT * FROM meme_auto_journal ORDER BY id DESC LIMIT 12')]}


def _log(c,now,address,action,note):
    c.execute('INSERT INTO meme_auto_journal(timestamp,address,action,note) VALUES(?,?,?,?)',
              (now,address,action,note[:280]))


def decide_exit(position,price,now):
    """Return stop, target, timeout, or None; evaluate on estimated SELL proceeds."""
    p=_number(price)
    if p is None or p<=0:return None
    cost=_number(position['cost_usd'])
    qty=_number(position['quantity'])
    opened=position['opened_at']
    if cost is None or cost<=0 or qty is None or qty<=0:return None
    from meme_demo import SELL_COST
    net=qty*p*(1-SELL_COST)
    roi=net/cost-1
    if roi<=STOP_LOSS:return 'STOP_LOSS'
    if roi>=TAKE_PROFIT:return 'TAKE_PROFIT'
    if now-int(opened)>=MAX_HOLD_SECONDS:return 'TIMEOUT_2H'
    return None


def choose_candidate(c,candidates,now,exclude=None):
    """Choose one eligible mint, avoiding duplicates and same-mint churn."""
    if not isinstance(candidates,list):return None
    existing={r['address'] for r in c.execute('SELECT address FROM meme_demo_positions')}
    existing.update(exclude or ())
    ranked=[]
    for t in candidates[:12]:
        if not isinstance(t,dict):continue
        address=t.get('address')
        if not isinstance(address,str) or not ADDRESS.fullmatch(address) or address in existing:continue
        price=_number(t.get('price_usd'))
        liq=_number(t.get('liquidity_usd'))
        vol=_number(t.get('volume_24h_usd'))
        if price is None or price<=0 or liq is None or liq<MIN_AUTO_LIQUIDITY or vol is None or vol<MIN_AUTO_VOLUME:continue
        last=c.execute('SELECT MAX(timestamp) FROM meme_demo_trades WHERE address=?',(address,)).fetchone()[0]
        if last is not None and now-int(last)<COOLDOWN_SECONDS:continue
        ranked.append((liq,vol,t))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
    return ranked[0][2] if ranked else None


def tick(c,now=None,scout=scan,quote=indicative_quote):
    """One complete bounded cycle. Caller holds the server DB mutex.
    This routine is designed for synchronous test injection. Network calls can
    fail independently; no action occurs without valid server-fetched prices.
    """
    now=int(time.time()) if now is None else int(now)
    init_auto(c)
    a=c.execute('SELECT * FROM meme_auto_state WHERE id=1').fetchone()
    if not a['enabled']:return status(c)
    messages=[]
    positions=[dict(p) for p in c.execute('SELECT * FROM meme_demo_positions ORDER BY opened_at')]
    for pos in positions[:MAX_POSITIONS]:
        address=pos['address']
        try:
            q=quote(address)
            price=_number(q.get('price_usd'))
            if price is None or price<=0:raise ValueError('Prezzo assente')
            c.execute('UPDATE meme_demo_positions SET last_price_usd=?,last_checked_at=? WHERE address=?',
                      (price,now,address))
            reason=decide_exit(pos,price,now)
            if reason:
                result=quick_trade(c,address,'SELL',q,now=now)
                _log(c,now,address,'AUTO_SELL',reason+' · pnl_credits='+str(result['pnl_usd']))
                messages.append('SELL '+reason)
        except (OSError,ValueError,TypeError,KeyError,OverflowError,TimeoutError) as exc:
            messages.append('QUOTE_NON_DISPONIBILE '+type(exc).__name__)
    if now-int(a['last_scan'])>=SCAN_SECONDS:
        # Mark attempt before network call, to prevent frequent requests on errors.
        c.execute('UPDATE meme_auto_state SET last_scan=? WHERE id=1',(now,))
        try:
            report=scout()
            rows=report.get('candidates',[]) if isinstance(report,dict) else []
            positions_count=c.execute('SELECT COUNT(*) FROM meme_demo_positions').fetchone()[0]
            opened=0
            considered=set()
            # Multiple independent token entries per discovery scan, capped by
            # both position count and available demo credits. Never repeat a mint.
            while positions_count<MAX_POSITIONS and opened<MAX_ENTRIES_PER_SCAN:
                available=float(c.execute(
                    'SELECT cash_usd FROM meme_demo_account WHERE id=1').fetchone()[0])
                if available+1e-9<STAKE_USD:
                    messages.append('CREDITI_DEMO_INSUFFICIENTI')
                    break
                selected=choose_candidate(c,rows,now,exclude=considered)
                if not selected:
                    if opened==0:messages.append('NESSUN_CANDIDATO_IDONEO')
                    break
                mint=selected['address']
                considered.add(mint)
                try:
                    # Independent public quote: no frontend-supplied price.
                    current=quote(mint)
                    price=_number(current.get('price_usd'))
                    liquidity=_number(current.get('liquidity_usd'))
                    volume=_number(current.get('volume_24h_usd'))
                    if (price is None or price<=0 or liquidity is None
                            or liquidity<MIN_AUTO_LIQUIDITY or volume is None
                            or volume<MIN_AUTO_VOLUME):
                        messages.append('CANDIDATO_QUOTE_NON_IDONEA')
                        continue
                    trade=quick_trade(c,mint,'BUY',current,now=now)
                    _log(c,now,mint,'AUTO_BUY',
                         'Test '+str(trade['cost_usd'])+' crediti · regole sperimentali, sicurezza NON verificata')
                    messages.append('AUTO_BUY '+mint[:8])
                    positions_count+=1
                    opened+=1
                except (OSError,ValueError,TypeError,KeyError,OverflowError,TimeoutError) as exc:
                    messages.append('CANDIDATO_NON_DISPONIBILE '+type(exc).__name__)
            if positions_count>=MAX_POSITIONS:messages.append('LIMITE_POSIZIONI')
        except (OSError,ValueError,TypeError,KeyError,OverflowError,TimeoutError) as exc:
            messages.append('SCOUT_NON_DISPONIBILE '+type(exc).__name__)
    label=' · '.join(messages) if messages else 'MONITORAGGIO'
    c.execute('UPDATE meme_auto_state SET last_tick=?,last_status=?,last_error=? WHERE id=1',
              (now,label[:250],'' if not any('NON_DISPONIBILE' in x for x in messages) else label[:250]))
    c.commit()
    return status(c)
