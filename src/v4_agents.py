"""NEXUS 4.0 — isolated autonomous multi-agent PAPER experiment.

Only persisted, genuinely received DEX Screener REST snapshots; no API calls
and no real-order code. Four deterministic agents, NOT four independent LLMs.
Dedicated EUR-denominated virtual account, synthetic price-ratio exposure
(no USD/EUR FX conversion or actual fills). Cannot affect legacy wallets.
"""
import math
import time

INITIAL_EUR=500.0
MAX_POSITIONS=3
MAX_ALLOCATION=0.05
BUY_COST=0.03
SELL_COST=0.03
MAX_DRAWDOWN=0.10
MIN_LIQUIDITY_USD=20000.0
MIN_VOLUME_24H_USD=50000.0
MAX_QUOTE_AGE=45
MAX_HOLD_SECONDS=900
MAX_ENTRY_PER_CYCLE=1
COOLDOWN_SECONDS=3600

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS v4_paper_state(
        id INTEGER PRIMARY KEY CHECK(id=1),
        enabled INTEGER NOT NULL DEFAULT 1,
        cash_eur REAL NOT NULL DEFAULT 500,
        initial_eur REAL NOT NULL DEFAULT 500,
        peak_equity_eur REAL NOT NULL DEFAULT 500,
        risk_latched INTEGER NOT NULL DEFAULT 0,
        last_tick INTEGER NOT NULL DEFAULT 0,
        last_decision TEXT NOT NULL DEFAULT 'WAITING_DATA')""")
    c.execute("INSERT OR IGNORE INTO v4_paper_state(id) VALUES(1)")
    c.execute("""CREATE TABLE IF NOT EXISTS v4_paper_positions(
        address TEXT PRIMARY KEY,symbol TEXT NOT NULL,
        opened_at INTEGER NOT NULL,entry_price_usd REAL NOT NULL,
        last_price_usd REAL NOT NULL,last_quote_at INTEGER NOT NULL,
        stake_eur REAL NOT NULL,synthetic_qty REAL NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS v4_paper_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,address TEXT NOT NULL,
        symbol TEXT NOT NULL,side TEXT NOT NULL,reason TEXT NOT NULL,
        price_usd REAL NOT NULL,amount_eur REAL NOT NULL,
        pnl_eur REAL,model_fee_pct REAL NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS v4_agent_decisions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,address TEXT,symbol TEXT,
        action TEXT NOT NULL,reason TEXT NOT NULL,
        agents_json TEXT NOT NULL)""")

def _number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>0 else None
    except (TypeError,ValueError,OverflowError):
        return None

def _latest(c,now):
    from meme_prices import initialize as init_prices
    init_prices(c)
    return [dict(x) for x in c.execute("""SELECT * FROM meme_quote_latest
        WHERE observed_at>=? ORDER BY observed_at DESC,address LIMIT 20""",
        (now-MAX_QUOTE_AGE,))]

def _history(c,address,now):
    return [dict(x) for x in c.execute("""SELECT observed_at,price_usd FROM meme_quote_changes
        WHERE address=? AND observed_at>=? ORDER BY id DESC LIMIT 12""",
        (address,now-600)).fetchall()][::-1]

def agents_decide(row,history):
    """Independent rule checks; cautious verdict not a security certification."""
    price=_number(row.get('price_usd'))
    liq=_number(row.get('liquidity_usd'))
    vol=_number(row.get('volume_24h_usd'))
    evidence={'analyst':'INSUFFICIENT','risk':'UNKNOWN',
              'strategy':'WAIT','portfolio':'BUDGET_PENDING'}
    if not price or not liq or not vol:
        return 'WAIT','Prezzo, liquidita o volume non disponibili',evidence
    evidence['risk']='SCANNER_ONLY_NOT_SECURITY_VERIFIED'
    if liq<MIN_LIQUIDITY_USD or vol<MIN_VOLUME_24H_USD:
        evidence['risk']='LOW_LIQUIDITY_OR_VOLUME'
        return 'WAIT','Filtri di mercato insufficienti; sicurezza non verificata',evidence
    prices=[_number(x.get('price_usd')) for x in history]
    prices=[p for p in prices if p is not None]
    if len(prices)<3:
        return 'WAIT','Servono almeno tre variazioni REST realmente osservate',evidence
    if max(prices)/min(prices)>1.5:
        evidence['risk']='VOLATILITY_SPIKE'
        return 'WAIT','Escursione superiore al 50%: rischio elevato',evidence
    momentum=price/prices[0]-1
    recent=price/prices[-2]-1
    evidence['analyst']='MOMENTUM_'+format(momentum*100,'.2f')+'PCT'
    if not (0.02<=momentum<=0.12 and -0.01<=recent<=0.08):
        return 'WAIT','Momentum non confermato dai campioni REST',evidence
    evidence['strategy']='PAPER_ENTRY_CANDIDATE'
    return 'BUY','Segnale PAPER: momentum e filtri scanner superati; vendibilita sconosciuta',evidence

def _equity(c,state):
    equity=float(state['cash_eur'])
    for p in c.execute('SELECT * FROM v4_paper_positions'):
        price=_number(p['last_price_usd'])
        if price:equity+=float(p['synthetic_qty'])*price*(1-SELL_COST)
    return round(equity,6)

def _log(c,now,address,symbol,action,reason,agents):
    import json
    c.execute("""INSERT INTO v4_agent_decisions(
        timestamp,address,symbol,action,reason,agents_json) VALUES(?,?,?,?,?,?)""",
        (now,address,symbol,action,str(reason)[:220],
         json.dumps(agents,ensure_ascii=False,sort_keys=True)))

def tick(c,now=None):
    """One autonomous PAPER cycle. Runs only on observed quotes, no mock fills."""
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    state=c.execute('SELECT * FROM v4_paper_state WHERE id=1').fetchone()
    if not state['enabled']:
        c.execute("UPDATE v4_paper_state SET last_tick=?,last_decision='SUSPENDED' WHERE id=1",(now,))
        return {'status':'SUSPENDED','new_trades':0}
    latest=_latest(c,now)
    by_address={r['address']:r for r in latest}
    # Revalue ONLY positions with a sufficiently recent *actual* REST quote.
    for p in c.execute('SELECT address FROM v4_paper_positions'):
        quote=by_address.get(p['address'])
        if quote and _number(quote['price_usd']):
            c.execute("""UPDATE v4_paper_positions SET last_price_usd=?,
                last_quote_at=? WHERE address=?""",
                (quote['price_usd'],quote['observed_at'],p['address']))
    state=c.execute('SELECT * FROM v4_paper_state WHERE id=1').fetchone()
    equity=_equity(c,state)
    peak=max(float(state['peak_equity_eur']),equity)
    latched=bool(state['risk_latched']) or equity<=peak*(1-MAX_DRAWDOWN)
    if latched:
        c.execute("""UPDATE v4_paper_state SET risk_latched=1,
            peak_equity_eur=? WHERE id=1""",(peak,))
    elif peak>state['peak_equity_eur']:
        c.execute('UPDATE v4_paper_state SET peak_equity_eur=? WHERE id=1',(peak,))
    completed=0
    for p in c.execute('SELECT * FROM v4_paper_positions ORDER BY opened_at').fetchall():
        quote=by_address.get(p['address'])
        if not quote:continue # no execution inferred from stale marks
        price=_number(quote['price_usd'])
        if not price:continue
        change=price/float(p['entry_price_usd'])-1
        proceeds=float(p['synthetic_qty'])*price*(1-SELL_COST)
        pnl=proceeds-float(p['stake_eur'])
        net_change=pnl/float(p['stake_eur'])
        reason=('STOP_GROSS_MINUS_5' if change<=-0.05 else
                'EMERGENCY_NET_MINUS_15' if net_change<=-0.15 else
                'TAKE_PROFIT_NET_12' if net_change>=0.12 else
                'TIMEOUT_15_MIN' if now-int(p['opened_at'])>=MAX_HOLD_SECONDS else None)
        if reason is None:continue
        c.execute('DELETE FROM v4_paper_positions WHERE address=?',(p['address'],))
        c.execute('UPDATE v4_paper_state SET cash_eur=cash_eur+? WHERE id=1',(proceeds,))
        c.execute("""INSERT INTO v4_paper_trades(
            timestamp,address,symbol,side,reason,price_usd,amount_eur,pnl_eur,model_fee_pct)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (now,p['address'],p['symbol'],'SELL_PAPER',reason,price,proceeds,pnl,SELL_COST*100))
        _log(c,now,p['address'],p['symbol'],'SELL_PAPER',reason,
             {'risk':'EXIT_RULE','strategy':'PAPER_EXIT','analyst':'ACTUAL_REST_SAMPLE',
              'portfolio':'SIMULATED_FEE'})
        completed+=1
    state=c.execute('SELECT * FROM v4_paper_state WHERE id=1').fetchone()
    equity=_equity(c,state)
    peak=max(float(state['peak_equity_eur']),equity)
    if equity<=peak*(1-MAX_DRAWDOWN):
        latched=True
        c.execute('UPDATE v4_paper_state SET risk_latched=1 WHERE id=1')
    blocked=bool(state['risk_latched']) or latched
    positions=c.execute('SELECT COUNT(*) FROM v4_paper_positions').fetchone()[0]
    decision='RISK_LOCK' if blocked else 'NO_ELIGIBLE_SIGNAL'
    if not blocked and positions<MAX_POSITIONS:
        for quote in latest:
            addr=quote['address']
            if c.execute('SELECT 1 FROM v4_paper_positions WHERE address=?',(addr,)).fetchone():
                continue
            last=c.execute("""SELECT MAX(timestamp) FROM v4_paper_trades
                WHERE address=?""",(addr,)).fetchone()[0]
            if last is not None and now-int(last)<COOLDOWN_SECONDS:continue
            history=_history(c,addr,now)
            vote,reason,agents=agents_decide(quote,history)
            stake=round(min(INITIAL_EUR*MAX_ALLOCATION,float(state['cash_eur'])),2)
            agents['portfolio']='MAX_5PCT_3_POSITIONS' if stake>=1 else 'LOW_CASH'
            if vote!='BUY' or stake<1:
                continue
            # Opt-in was explicit in project planning; legacy account untouched.
            qty=stake*(1-BUY_COST)/float(quote['price_usd'])
            c.execute("""INSERT INTO v4_paper_positions(
                address,symbol,opened_at,entry_price_usd,last_price_usd,last_quote_at,
                stake_eur,synthetic_qty) VALUES(?,?,?,?,?,?,?,?)""",
                (addr,quote['symbol'],now,quote['price_usd'],
                 quote['price_usd'],quote['observed_at'],stake,qty))
            c.execute('UPDATE v4_paper_state SET cash_eur=cash_eur-? WHERE id=1',(stake,))
            c.execute("""INSERT INTO v4_paper_trades(
                timestamp,address,symbol,side,reason,price_usd,amount_eur,pnl_eur,model_fee_pct)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (now,addr,quote['symbol'],'BUY_PAPER',reason,quote['price_usd'],
                 stake,None,BUY_COST*100))
            _log(c,now,addr,quote['symbol'],'BUY_PAPER',reason,agents)
            completed+=1
            decision='BUY_PAPER'
            break
    if blocked:decision='RISK_LOCK'
    c.execute('UPDATE v4_paper_state SET last_tick=?,last_decision=? WHERE id=1',
              (now,decision))
    return {'status':decision,'new_trades':completed}

def report(c,now=None):
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    state=dict(c.execute('SELECT * FROM v4_paper_state WHERE id=1').fetchone())
    positions=[dict(p) for p in c.execute(
        'SELECT * FROM v4_paper_positions ORDER BY opened_at DESC')]
    trades=[dict(t) for t in c.execute(
        'SELECT * FROM v4_paper_trades ORDER BY id DESC LIMIT 20')]
    decisions=[dict(d) for d in c.execute(
        'SELECT * FROM v4_agent_decisions ORDER BY id DESC LIMIT 15')]
    equity=_equity(c,state)
    for p in positions:
        p['quote_age_seconds']=max(0,now-int(p['last_quote_at']))
        p['stale_quote']=p['quote_age_seconds']>MAX_QUOTE_AGE
        p['modeled_net_pnl_eur']=round(
            p['synthetic_qty']*p['last_price_usd']*(1-SELL_COST)-p['stake_eur'],4)
    sells=[t for t in trades if t['side']=='SELL_PAPER']
    return {'mode':'ISOLATED_MULTIAGENT_PAPER','engine':'DETERMINISTIC_AGENTS_NOT_LLM',
            'enabled':bool(state['enabled']),'cash_eur':round(state['cash_eur'],4),
            'initial_eur':INITIAL_EUR,'equity_eur':equity,
            'peak_equity_eur':state['peak_equity_eur'],
            'drawdown_pct':round((1-equity/max(.01,state['peak_equity_eur']))*100,3),
            'risk_latched':bool(state['risk_latched']),
            'last_tick':state['last_tick'],'last_decision':state['last_decision'],
            'max_positions':MAX_POSITIONS,'max_trade_pct':MAX_ALLOCATION*100,
            'positions':positions,'trades':trades,'decisions':decisions,
            'closed_count':c.execute("SELECT COUNT(*) FROM v4_paper_trades WHERE side='SELL_PAPER'").fetchone()[0],
            'trade_count':c.execute('SELECT COUNT(*) FROM v4_paper_trades').fetchone()[0],
            'security_verified':False,'real_trades_enabled':False,
            'warning':('Agenti a regole deterministiche, NON modelli IA indipendenti. '
             '500 EUR solo virtuali separati dal portafoglio legacy. '
             'Quantita sintetiche, variazione di prezzo USD applicata a capitale '
             'virtuale EUR senza conversione FX; commissioni 3% per lato modellate. '
             'Controlli on-chain e vendibilita NON verificati. Prezzi REST non eseguibili. '
             'Questo portafoglio non sblocca il Risk Lock precedente.')}
