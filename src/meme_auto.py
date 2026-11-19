"""Autonomous Solana MEME trading simulation on the original €45 NEXUS wallet.

Only market-data requests and local SQLite bookkeeping. NEVER real orders,
signatures, wallet keys, swaps, or trade API calls. Experimental signals.
"""
import math
import time
from meme_portfolio import (initialize,trade,mark,portfolio,get_fx,indicative_quote,
                            MAX_POSITIONS, STAKE_EUR, SELL_COST)
from meme_scout import scan,ADDRESS

STOP_LOSS=-0.10
TAKE_PROFIT=0.20
MAX_HOLD_SECONDS=7200
SCAN_SECONDS=300
COOLDOWN_SECONDS=3600
MIN_AUTO_LIQUIDITY=500.0
MIN_AUTO_VOLUME=500.0
MAX_ENTRIES_PER_SCAN=3

def _number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>=0 else None
    except (TypeError,ValueError,OverflowError):return None

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
        id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp INTEGER NOT NULL,
        address TEXT, action TEXT NOT NULL,note TEXT NOT NULL)''')

def status(c):
    init_auto(c)
    s=c.execute('SELECT * FROM meme_auto_state WHERE id=1').fetchone()
    return {'enabled':bool(s['enabled']),'last_scan':s['last_scan'],
            'last_tick':s['last_tick'],'status':s['last_status'],
            'error':s['last_error'],'stop_loss_pct':-10,'take_profit_pct':20,
            'max_hold_minutes':120,'monitor_seconds':30,'scan_seconds':SCAN_SECONDS,
            'max_positions':MAX_POSITIONS,'max_entries_per_scan':MAX_ENTRIES_PER_SCAN,
            'mode':'AUTONOMOUS_PAPER_ONLY',
            'journal':[dict(x) for x in c.execute(
                'SELECT * FROM meme_auto_journal ORDER BY id DESC LIMIT 12')]}

def _log(c,now,address,action,note):
    c.execute('INSERT INTO meme_auto_journal(timestamp,address,action,note) VALUES(?,?,?,?)',
              (now,address,action,note[:280]))

def decide_exit(p,price,now,fx=None):
    """Thresholds use expected net EUR proceeds, including model SELL costs."""
    price=_number(price)
    if price is None or price<=0:return None
    qty=_number(p.get('quantity'))
    cost=_number(p.get('cost_eur'))
    exchange=_number(fx if fx is not None else p.get('last_fx_usd_eur'))
    if not qty or not cost or not exchange:return None
    roi=qty*price*exchange*(1-SELL_COST)/cost-1
    if roi<=STOP_LOSS:return 'STOP_LOSS'
    if roi>=TAKE_PROFIT:return 'TAKE_PROFIT'
    if now-int(p['opened_at'])>=MAX_HOLD_SECONDS:return 'TIMEOUT_2H'
    return None

def eligible_candidates(c,candidates,now,excluded=None):
    if not isinstance(candidates,list):return []
    existing={p['address'] for p in c.execute('SELECT address FROM meme_eur_positions')}
    existing.update(excluded or ())
    ranked=[]
    seen=set()
    for t in candidates[:12]:
        if not isinstance(t,dict):continue
        address=t.get('address')
        if (not isinstance(address,str) or not ADDRESS.fullmatch(address)
                or address in existing or address in seen):continue
        seen.add(address)
        price=_number(t.get('price_usd'))
        liq=_number(t.get('liquidity_usd'))
        vol=_number(t.get('volume_24h_usd'))
        if not price or liq is None or liq<MIN_AUTO_LIQUIDITY or vol is None or vol<MIN_AUTO_VOLUME:continue
        previous=c.execute('SELECT MAX(timestamp) FROM meme_eur_trades WHERE address=?',(address,)).fetchone()[0]
        if previous is not None and now-int(previous)<COOLDOWN_SECONDS:continue
        ranked.append((liq,vol,t))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
    return [t for _,_,t in ranked]

def choose_candidate(c,candidates,now,exclude=None):
    choices=eligible_candidates(c,candidates,now,exclude)
    return choices[0] if choices else None

def tick(c,now=None,scout=scan,quote=indicative_quote,fx_rate=get_fx):
    """One cycle. Caller holds server mutex; all fills remain virtual."""
    now=int(time.time()) if now is None else int(now)
    init_auto(c)
    a=c.execute('SELECT * FROM meme_auto_state WHERE id=1').fetchone()
    if not a['enabled']:return status(c)
    messages=[]
    fx=None
    try:
        fx=fx_rate(c,now=now)
    except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
        messages.append('CAMBIO_USD_EUR_NON_DISPONIBILE '+type(exc).__name__)
    positions=[dict(p) for p in c.execute('SELECT * FROM meme_eur_positions ORDER BY opened_at')]
    if fx is not None:
        for pos in positions[:MAX_POSITIONS]:
            addr=pos['address']
            try:
                q=quote(addr)
                price=_number(q.get('price_usd'))
                if price is None or price<=0:raise ValueError('Quotazione non valida')
                mark(c,addr,q,fx,now=now)
                reason=decide_exit(pos,price,now,fx['usd_eur'])
                if reason:
                    result=trade(c,addr,'SELL',q,fx,now=now)
                    _log(c,now,addr,'AUTO_SELL',reason+' · pnl_eur='+str(result['pnl_eur']))
                    messages.append('AUTO_SELL '+reason)
            except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
                messages.append('QUOTE_NON_DISPONIBILE '+type(exc).__name__)
    if now-int(a['last_scan'])>=SCAN_SECONDS:
        c.execute('UPDATE meme_auto_state SET last_scan=? WHERE id=1',(now,))
        if fx is None:
            messages.append('SCAN_SOSPESO_SENZA_CAMBIO')
        else:
            try:
                report=scout()
                rows=report.get('candidates',[]) if isinstance(report,dict) else []
                count=c.execute('SELECT COUNT(*) FROM meme_eur_positions').fetchone()[0]
                bought=0
                candidates=eligible_candidates(c,rows,now)
                for candidate in candidates:
                    if bought>=MAX_ENTRIES_PER_SCAN or count>=MAX_POSITIONS:break
                    cash=float(c.execute("SELECT cash FROM wallets WHERE strategy='meme'").fetchone()[0])
                    if cash+1e-9<STAKE_EUR:
                        messages.append('FONDI_MEME_VIRTUALI_INSUFFICIENTI')
                        break
                    mint=candidate['address']
                    try:
                        q=quote(mint)
                        p=_number(q.get('price_usd'))
                        liquidity=_number(q.get('liquidity_usd'))
                        volume=_number(q.get('volume_24h_usd'))
                        if (not p or liquidity is None or liquidity<MIN_AUTO_LIQUIDITY
                                or volume is None or volume<MIN_AUTO_VOLUME):
                            messages.append('CANDIDATO_QUOTE_NON_IDONEA')
                            continue
                        result=trade(c,mint,'BUY',q,fx,now=now)
                        _log(c,now,mint,'AUTO_BUY','EUR '+str(result['cost_eur'])+
                             ' · paper · vendibilità NON verificata')
                        bought+=1
                        count+=1
                        messages.append('AUTO_BUY '+mint[:8])
                    except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
                        messages.append('CANDIDATO_NON_DISPONIBILE '+type(exc).__name__)
                if count>=MAX_POSITIONS:messages.append('LIMITE_POSIZIONI')
                elif bought==0 and not any(x.startswith('CANDIDATO_') for x in messages):
                    messages.append('NESSUN_CANDIDATO_IDONEO')
            except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
                messages.append('SCOUT_NON_DISPONIBILE '+type(exc).__name__)
    label=' · '.join(messages) if messages else 'MONITORAGGIO'
    errors=[m for m in messages if 'NON_DISPONIBILE' in m or 'SOSPESO_SENZA' in m]
    c.execute('UPDATE meme_auto_state SET last_tick=?,last_status=?,last_error=? WHERE id=1',
              (now,label[:250],'; '.join(errors)[:250]))
    c.commit()
    return status(c)
