"""NEXUS Strategy Intelligence: historical PAPER attribution and observational watchlist.

Read-only strategy reporting except for bounded observed candidate facts. No
wallet changes, simulated fills, retroactive prices, or model API requests.
"""
import math
import time
from collections import Counter
from meme_scout import ADDRESS
from meme_demo import BUY_COST, SELL_COST

MAX_OBSERVED=12
MAX_HISTORY=400
MAX_AGE_SECONDS=48*3600

def _n(value):
    try:
        value=float(value)
        return value if math.isfinite(value) and value>=0 else None
    except (TypeError,ValueError,OverflowError):
        return None

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS meme_observed_candidates(
        address TEXT PRIMARY KEY, symbol TEXT NOT NULL,
        first_seen INTEGER NOT NULL,last_seen INTEGER NOT NULL,
        first_price_usd REAL NOT NULL,last_price_usd REAL NOT NULL,
        first_liquidity_usd REAL, last_liquidity_usd REAL,
        last_volume_usd REAL, observation_count INTEGER NOT NULL,
        status TEXT NOT NULL)""")

def observe_blocked(c,candidates,now=None,reason='DRAWDOWN_CIRCUIT'):
    """Watch market observations without placing an order; no extra network calls.

    Deliberately uses only data in already-retrieved scanner results. Baselines
    never get relabeled as fills, and unchanged snapshots are not price ticks.
    """
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    seen=set()
    accepted=0
    for row in candidates[:30] if isinstance(candidates,list) else []:
        if not isinstance(row,dict):continue
        addr=row.get('address')
        if not isinstance(addr,str) or not ADDRESS.fullmatch(addr) or addr in seen:continue
        seen.add(addr)
        price=_n(row.get('price_usd'))
        if not price or price<=0:continue
        liquidity=_n(row.get('liquidity_usd'))
        volume=_n(row.get('volume_24h_usd'))
        existing=c.execute('SELECT * FROM meme_observed_candidates WHERE address=?',(addr,)).fetchone()
        if existing:
            c.execute("""UPDATE meme_observed_candidates SET last_seen=?,
                last_price_usd=?,last_liquidity_usd=?,last_volume_usd=?,
                observation_count=observation_count+1,status=?
                WHERE address=?""",(now,price,liquidity,volume,reason,addr))
        else:
            c.execute("""INSERT INTO meme_observed_candidates(
                address,symbol,first_seen,last_seen,first_price_usd,last_price_usd,
                first_liquidity_usd,last_liquidity_usd,last_volume_usd,
                observation_count,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (addr,str(row.get('symbol') or '?')[:24],now,now,price,price,
                 liquidity,liquidity,volume,1,reason))
        accepted+=1
        if accepted>=MAX_OBSERVED:break
    c.execute('DELETE FROM meme_observed_candidates WHERE last_seen<?',
              (now-MAX_AGE_SECONDS,))
    c.execute("""DELETE FROM meme_observed_candidates WHERE address NOT IN
        (SELECT address FROM meme_observed_candidates
         ORDER BY last_seen DESC,address LIMIT ?)""",(MAX_HISTORY,))
    return accepted

def _trade_attribution(c):
    """Reconstruct only fully matched historical BUY/SELL pairs (no guesses)."""
    trades=[dict(r) for r in c.execute(
        'SELECT * FROM meme_eur_trades ORDER BY id ASC')]
    outstanding={}
    closed=[]
    unmatched_sells=0
    for t in trades:
        if t['action']=='BUY':
            outstanding[t['address']]=t
            continue
        if t['action']!='SELL':continue
        buy=outstanding.pop(t['address'],None)
        if not buy:
            unmatched_sells+=1
            continue
        qty=_n(t['quantity'])
        sell_price=_n(t['price_usd'])
        sell_fx=_n(t['fx_usd_eur'])
        buy_price=_n(buy['price_usd'])
        buy_fx=_n(buy['fx_usd_eur'])
        spent=_n(buy['cash_eur'])
        pnl=t['pnl_eur']
        if any(x is None for x in (qty,sell_price,sell_fx,buy_price,buy_fx,spent,pnl)):
            unmatched_sells+=1
            continue
        net=float(pnl)
        gross_entry=qty*buy_price*buy_fx
        gross_exit=qty*sell_price*sell_fx
        # The model charges BUY_COST on acquisition and SELL_COST on disposal.
        fee_drag=max(0.0,(spent-gross_entry)+(gross_exit*(SELL_COST)))
        observed_price_delta=(gross_exit/gross_entry-1)*100 if gross_entry else None
        reason=c.execute("""SELECT note FROM meme_auto_journal
            WHERE address=? AND action='AUTO_SELL' AND timestamp BETWEEN ? AND ?
            ORDER BY ABS(timestamp-?),id DESC LIMIT 1""",
            (t['address'],int(t['timestamp'])-1,int(t['timestamp'])+1,int(t['timestamp']))).fetchone()
        if reason:
            exit_reason=str(reason['note']).split(' · ',1)[0]
        elif 'PAPER' in str(t.get('note') or ''):
            exit_reason='MANUALE_O_NON_ATTRIBUIBILE'
        else:
            exit_reason='NON_ATTRIBUIBILE'
        closed.append({
            'address':t['address'],'symbol':t['symbol'],
            'closed_at':t['timestamp'],'opened_at':buy['timestamp'],
            'duration_seconds':max(0,int(t['timestamp'])-int(buy['timestamp'])),
            'stake_eur':round(spent,5),
            'pnl_eur':round(net,7),
            'estimated_fee_drag_eur':round(fee_drag,7),
            'gross_price_fx_change_pct':round(observed_price_delta,4) if observed_price_delta is not None else None,
            'exit_reason':exit_reason})
    return closed,len(outstanding),unmatched_sells

def report(c,now=None):
    """Produce separate history stats and candidate OBSERVATIONS, not backtests."""
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    closed,unmatched_buys,unmatched_sells=_trade_attribution(c)
    total=len(closed)
    winners=sum(item['pnl_eur']>0 for item in closed)
    losers=sum(item['pnl_eur']<0 for item in closed)
    pnl=sum(item['pnl_eur'] for item in closed)
    fee_drag=sum(item['estimated_fee_drag_eur'] for item in closed)
    by_reason=Counter(item['exit_reason'] for item in closed)
    observations=[]
    for row in c.execute("""SELECT * FROM meme_observed_candidates
        ORDER BY last_seen DESC,address LIMIT 30"""):
        d=dict(row)
        change=(d['last_price_usd']/d['first_price_usd']-1)*100
        observations.append({
            'address':d['address'],'symbol':d['symbol'],
            'first_seen':d['first_seen'],'last_seen':d['last_seen'],
            'observations':d['observation_count'],
            'first_price_usd':d['first_price_usd'],
            'last_price_usd':d['last_price_usd'],
            'observed_change_pct':round(change,3) if d['observation_count']>=2 else None,
            'last_liquidity_usd':d['last_liquidity_usd'],
            'last_volume_usd':d['last_volume_usd'],
            'status':d['status']})
    from meme_auto import circuit_breaker
    return {
        'ok':True,'mode':'PAPER_HISTORY_AND_OBSERVATIONS',
        'guard':circuit_breaker(c,now),
        'history':{
            'matched_closed':total,'wins':winners,'losses':losers,
            'win_rate_pct':round(100*winners/total,2) if total else None,
            'realized_pnl_eur':round(pnl,6),
            'estimated_fee_drag_eur':round(fee_drag,6),
            'unmatched_buys':unmatched_buys,'unmatched_sells':unmatched_sells,
            'by_exit_reason':[{'reason':reason,'count':count}
                for reason,count in sorted(by_reason.items())],
            'recent':list(reversed(closed[-20:]))
        },
        'watchlist':observations,
        'disclaimer':('Storico ordini PAPER gia registrati. Costi stimati dal modello 3% per lato. '
            'La watchlist riporta soltanto prezzi REST osservati in piu scansioni: '
            'non e un backtest, non dimostra che un acquisto o una vendita '
            'sarebbero stati eseguibili. Nessuna operazione e effettuata qui.')
    }
