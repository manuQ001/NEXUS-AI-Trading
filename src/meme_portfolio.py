"""MEME PAPER portfolio denominated in EUR, backed by the existing NEXUS meme wallet.

Prices are USD indicative DEX Screener quotes. FX is daily USD/EUR reference
from Frankfurter; FX source/date and assumed fees must be shown. NO live orders.
The old USD-demo positions and history are retained in legacy SQLite tables as
read-only archive. They are NOT converted into EUR fills retroactively.
"""
import json
import math
import time
from datetime import date,datetime,timezone
from urllib.request import Request,urlopen
from meme_scout import ADDRESS
from meme_demo import indicative_quote, BUY_COST, SELL_COST

STAKE_EUR=3.0
MAX_POSITIONS=8
FX_URL='https://api.frankfurter.dev/v2/rate/usd/eur'
FX_MAX_AGE_SECONDS=3*86400

def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS meme_eur_positions(
        address TEXT PRIMARY KEY, symbol TEXT NOT NULL, quantity REAL NOT NULL,
        entry_price_usd REAL NOT NULL, entry_fx_usd_eur REAL NOT NULL,
        cost_eur REAL NOT NULL, opened_at INTEGER NOT NULL,
        last_price_usd REAL NOT NULL,last_fx_usd_eur REAL NOT NULL,
        last_checked_at INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meme_eur_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp INTEGER NOT NULL,
        address TEXT NOT NULL,symbol TEXT NOT NULL,action TEXT NOT NULL,
        quantity REAL NOT NULL,price_usd REAL NOT NULL,
        fx_usd_eur REAL NOT NULL,cash_eur REAL NOT NULL,pnl_eur REAL,
        note TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meme_fx_cache(
        id INTEGER PRIMARY KEY CHECK(id=1),usd_eur REAL NOT NULL,
        rate_date TEXT NOT NULL, fetched_at INTEGER NOT NULL)''')

def _rate_from_public_json():
    req=Request(FX_URL,headers={'Accept':'application/json','User-Agent':'NEXUS-Paper-EUR/1.0'})
    with urlopen(req,timeout=7) as response:
        if response.status!=200:raise ValueError('Cambio USD/EUR HTTP non valido')
        raw=response.read(15000+1)
    if len(raw)>15000:raise ValueError('Cambio USD/EUR risposta troppo grande')
    return json.loads(raw)

def _validated_fx(payload,now):
    if not isinstance(payload,dict) or payload.get('base')!='USD' or payload.get('quote')!='EUR':
        raise ValueError('Cambio USD/EUR non valido')
    try:rate=float(payload['rate'])
    except (KeyError,ValueError,TypeError,OverflowError):raise ValueError('Tasso di cambio non valido')
    if not math.isfinite(rate) or not 0.3<=rate<=2:raise ValueError('Tasso di cambio fuori range')
    try:fx_date=date.fromisoformat(payload['date'])
    except (KeyError,TypeError,ValueError):raise ValueError('Data cambio non valida')
    today=datetime.fromtimestamp(now,timezone.utc).date()
    if fx_date>today or (today-fx_date).days>5:
        raise ValueError('Cambio di riferimento troppo vecchio')
    return rate,str(fx_date)

def get_fx(c,fetch=_rate_from_public_json,now=None):
    """Valid cached daily reference; fail-closed when too stale."""
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    old=c.execute('SELECT * FROM meme_fx_cache WHERE id=1').fetchone()
    if old and 0<=now-int(old['fetched_at'])<6*3600:
        return {'usd_eur':old['usd_eur'],'rate_date':old['rate_date'],
                'source':'Frankfurter (cache)','fetched_at':old['fetched_at']}
    try:
        rate,when=_validated_fx(fetch(),now)
        c.execute('''INSERT INTO meme_fx_cache(id,usd_eur,rate_date,fetched_at)
                     VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE
                     SET usd_eur=excluded.usd_eur,rate_date=excluded.rate_date,
                         fetched_at=excluded.fetched_at''',(rate,when,now))
        return {'usd_eur':rate,'rate_date':when,'source':'Frankfurter','fetched_at':now}
    except (OSError,ValueError,TypeError,KeyError,OverflowError,TimeoutError):
        if old and 0<=now-int(old['fetched_at'])<=FX_MAX_AGE_SECONDS:
            # Treat cached data as a reference, not a real-time FX tick.
            date.fromisoformat(old['rate_date'])
            if (datetime.fromtimestamp(now,timezone.utc).date()-date.fromisoformat(old['rate_date'])).days<=5:
                return {'usd_eur':old['usd_eur'],'rate_date':old['rate_date'],
                        'source':'Frankfurter (cache non aggiornabile)','fetched_at':old['fetched_at']}
        raise ValueError('Cambio USD/EUR non disponibile: nessuna operazione simulata')

def _positive(x,name):
    try:v=float(x)
    except (TypeError,ValueError,OverflowError):raise ValueError(name+' non valido')
    if not math.isfinite(v) or v<=0:raise ValueError(name+' non valido')
    return v

def _market_warnings(q):
    warnings=[]
    for key,label in (('liquidity_usd','liquidità'),('volume_24h_usd','volume 24h')):
        try:v=float(q.get(key))
        except (ValueError,TypeError,OverflowError):v=float('nan')
        if not math.isfinite(v) or v<0:warnings.append(label+' non disponibile')
        elif v<1000:warnings.append(label+' inferiore a $1000')
    return warnings

def trade(c,address,action,quote,fx,now=None):
    if action not in ('BUY','SELL'):raise ValueError('Azione non consentita')
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):raise ValueError('Mint non valido')
    if not isinstance(quote,dict):raise ValueError('Quotazione mancante')
    price=_positive(quote.get('price_usd'),'Prezzo USD')
    rate=_positive(fx.get('usd_eur') if isinstance(fx,dict) else fx,'USD/EUR')
    if not 0.3<=rate<=2:raise ValueError('Cambio USD/EUR non valido')
    now=int(time.time()) if now is None else int(now)
    symbol=str(quote.get('symbol') or '?')[:24]
    warnings=_market_warnings(quote)
    initialize(c)
    current=c.execute('SELECT * FROM meme_eur_positions WHERE address=?',(address,)).fetchone()
    wallet=c.execute("SELECT cash FROM wallets WHERE strategy='meme'").fetchone()
    if wallet is None:raise ValueError('Portafoglio MEME non inizializzato')
    if action=='BUY':
        if current:raise ValueError('Posizione già aperta su questo token')
        if c.execute('SELECT COUNT(*) FROM meme_eur_positions').fetchone()[0]>=MAX_POSITIONS:
            raise ValueError('Limite posizioni MEME raggiunto')
        if float(wallet['cash'])+1e-9<STAKE_EUR:
            raise ValueError('Liquidità virtuale MEME insufficiente')
        quantity=STAKE_EUR/(price*rate*(1+BUY_COST))
        if not math.isfinite(quantity) or quantity<=0:raise ValueError('Quantità token non valida')
        with c:
            c.execute("UPDATE wallets SET cash=cash-? WHERE strategy='meme'",(STAKE_EUR,))
            c.execute('INSERT INTO meme_eur_positions VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (address,symbol,quantity,price,rate,STAKE_EUR,now,price,rate,now))
            c.execute('''INSERT INTO meme_eur_trades(timestamp,address,symbol,action,quantity,
                       price_usd,fx_usd_eur,cash_eur,pnl_eur,note) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                      (now,address,symbol,'BUY',quantity,price,rate,STAKE_EUR,None,
                       'PAPER · ingresso EUR 3 · prezzo USD indicativo · cambio riferimento · costo modello 3%'))
        return {'ok':True,'action':'BUY','mode':'MEME_EUR_PAPER','cost_eur':STAKE_EUR,
                'warnings':warnings,'fx_usd_eur':rate}
    if current is None:raise ValueError('Nessuna posizione MEME aperta')
    proceeds=float(current['quantity'])*price*rate*(1-SELL_COST)
    if not math.isfinite(proceeds) or proceeds<0:raise ValueError('Proventi non validi')
    pnl=proceeds-float(current['cost_eur'])
    with c:
        c.execute("UPDATE wallets SET cash=cash+? WHERE strategy='meme'",(proceeds,))
        c.execute('DELETE FROM meme_eur_positions WHERE address=?',(address,))
        c.execute('''INSERT INTO meme_eur_trades(timestamp,address,symbol,action,quantity,
                   price_usd,fx_usd_eur,cash_eur,pnl_eur,note) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                  (now,address,current['symbol'],'SELL',current['quantity'],price,rate,proceeds,pnl,
                   'PAPER · uscita EUR simulata · prezzo indicativo · vendibilità non verificata · costo modello 3%'))
    return {'ok':True,'action':'SELL','mode':'MEME_EUR_PAPER','pnl_eur':round(pnl,8),
            'proceeds_eur':round(proceeds,8),'warnings':warnings,'fx_usd_eur':rate}

def mark(c,address,quote,fx,now=None):
    initialize(c)
    price=_positive(quote.get('price_usd'),'Prezzo USD')
    rate=_positive(fx.get('usd_eur') if isinstance(fx,dict) else fx,'USD/EUR')
    if not 0.3<=rate<=2:raise ValueError('Tasso USD/EUR invalido')
    now=int(time.time()) if now is None else int(now)
    c.execute('''UPDATE meme_eur_positions
                 SET last_price_usd=?,last_fx_usd_eur=?,last_checked_at=? WHERE address=?''',
              (price,rate,now,address))

def portfolio(c,now=None):
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    w=c.execute("SELECT * FROM wallets WHERE strategy='meme'").fetchone()
    if not w:raise ValueError('Portafoglio MEME assente')
    positions=[dict(x) for x in c.execute('SELECT * FROM meme_eur_positions ORDER BY opened_at DESC')]
    invested=0
    for p in positions:
        p['mark_age_seconds']=max(0,now-p['last_checked_at'])
        p['mark_status']='AGGIORNATO' if p['mark_age_seconds']<=90 else 'NON_AGGIORNATO'
        p['price_change_pct']=round((p['last_price_usd']/p['entry_price_usd']-1)*100,3)
        net=p['quantity']*p['last_price_usd']*p['last_fx_usd_eur']*(1-SELL_COST)
        p['estimated_net_value_eur']=round(net,8)
        p['estimated_pnl_eur']=round(net-p['cost_eur'],8)
        p['estimated_roi_pct']=round((net/p['cost_eur']-1)*100,3)
        invested+=net
    fx=c.execute('SELECT usd_eur,rate_date,fetched_at FROM meme_fx_cache WHERE id=1').fetchone()
    trades=[dict(t) for t in c.execute('SELECT * FROM meme_eur_trades ORDER BY id DESC LIMIT 50')]
    legacy=c.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="meme_demo_positions"').fetchone()
    legacy_count=c.execute('SELECT COUNT(*) FROM meme_demo_positions').fetchone()[0] if legacy else 0
    return {'mode':'MEME_EUR_PAPER','currency':'EUR','starting_eur':float(w['initial']),
            'cash_eur':round(float(w['cash']),8),'equity_eur':round(float(w['cash'])+invested,8),
            'stake_eur':STAKE_EUR,'max_positions':MAX_POSITIONS,
            'positions':positions,'trades':trades,
            'fx':dict(fx) if fx else None,
            'legacy_demo_positions_archived':legacy_count,
            'note':'Unico portafoglio MEME EUR, solo paper. Vecchi test USD demo non trasferiti e conservati nell archivio SQLite. Stima su prezzi USD osservati, FX di riferimento e costi modello 3% per lato; non prova vendibilità.'}
