"""Manual Meme Quick PAPER tests, isolated from the BTC/ETH engine and EUR wallets.

The USD demo credits are accounting units, not a conversion of the €45 MEME
allocation. Source is indicative DEX Screener pool price, not executable quotes.
No swaps, keys, wallet connections or transaction/signing libraries.
"""
import math
import time
import sqlite3
from meme_scout import _get_json, ADDRESS, PAIRS_ROOT

START_USD=45.0
STAKE_USD=3.0
MAX_POSITIONS=3
BUY_COST=0.03     # pessimistic model: 3% impact/fees per side
SELL_COST=0.03
MIN_LIQUIDITY=1000.0
MIN_VOLUME_24H=1000.0


def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS meme_demo_account(
        id INTEGER PRIMARY KEY CHECK(id=1), cash_usd REAL NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meme_demo_positions(
        address TEXT PRIMARY KEY, symbol TEXT NOT NULL,
        quantity REAL NOT NULL, entry_price_usd REAL NOT NULL,
        cost_usd REAL NOT NULL, opened_at INTEGER NOT NULL,
        last_price_usd REAL NOT NULL, last_checked_at INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meme_demo_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL,
        address TEXT NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL,
        quantity REAL NOT NULL, price_usd REAL NOT NULL,
        cost_usd REAL NOT NULL, pnl_usd REAL, note TEXT NOT NULL)''')
    c.execute('INSERT OR IGNORE INTO meme_demo_account(id,cash_usd) VALUES(1,45.0)')


def demo_state(c):
    initialize(c)
    cash=float(c.execute('SELECT cash_usd FROM meme_demo_account WHERE id=1').fetchone()[0])
    positions=[dict(x) for x in c.execute('SELECT * FROM meme_demo_positions ORDER BY opened_at DESC')]
    trades=[dict(x) for x in c.execute('SELECT * FROM meme_demo_trades ORDER BY id DESC LIMIT 30')]
    return {
        'mode':'DEMO_USD_PAPER','unit':'USD_demo','starting_credits':START_USD,
        'cash_credits':round(cash,6),'stake_credits':STAKE_USD,
        'positions':positions,'trades':trades,
        'nominal_last_mark_equity':round(cash+sum(
            p['quantity']*p['last_price_usd']*(1-SELL_COST) for p in positions),6),
        'note':'Credito USD demo isolato: NON è il conto MEME da €45 e non usa cambio EUR/USD. Ultimo prezzo osservato, non necessariamente attuale. Nessuna garanzia di vendibilità.'
    }


def indicative_quote(address, fetch=_get_json):
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):
        raise ValueError('Mint Solana non valido')
    raw=fetch(PAIRS_ROOT+address)
    if not isinstance(raw,list):raise ValueError('Fonte mercato mancante')
    eligible=[]
    for pair in raw[:60]:
        if not isinstance(pair,dict) or pair.get('chainId')!='solana':continue
        base=pair.get('baseToken')
        if not isinstance(base,dict) or base.get('address')!=address:continue
        def nonnegative(raw):
            try:
                v=float(raw)
                return v if math.isfinite(v) and v>=0 else None
            except (TypeError,ValueError,OverflowError):return None
        price=nonnegative(pair.get('priceUsd'))
        if price is None or price<=0:continue
        liquidity=pair.get('liquidity')
        volume=pair.get('volume')
        liq=nonnegative(liquidity.get('usd')) if isinstance(liquidity,dict) else None
        vol=nonnegative(volume.get('h24')) if isinstance(volume,dict) else None
        eligible.append({'price_usd':price,'liquidity_usd':liq,'volume_24h_usd':vol,
                         'symbol':str(base.get('symbol') or '?')[:24]})
    if not eligible:raise ValueError('Nessun prezzo USD valido per il mint selezionato')
    # Most liquid pair observed, but incomplete liquidity is allowed only for DEMO.
    return max(eligible,key=lambda q:q['liquidity_usd'] if q['liquidity_usd'] is not None else -1)


def quick_trade(c,address,action,quote,now=None):
    """Purely local PAPER execution; caller acquires shared DB lock.
    Quote always fetched server-side, never sent from the browser.
    Requires explicit user action and realistic-ish cost stress of 3% per side.
    """
    if action not in ('BUY','SELL'):raise ValueError('Azione non autorizzata')
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):
        raise ValueError('Mint Solana non valido')
    if not isinstance(quote,dict):raise ValueError('Dati mercato mancanti')
    try: price=float(quote['price_usd'])
    except (KeyError,TypeError,ValueError,OverflowError):raise ValueError('Prezzo non disponibile')
    if not math.isfinite(price) or price<=0:
        raise ValueError('Prezzo USD mancante o non valido')
    # For MANUAL DEMO, market quality is a warning, not an execution veto.
    # There is no claim of fill, depth or sellability. Actual orders remain impossible.
    def market_value(key):
        try:
            value=float(quote.get(key))
            return value if math.isfinite(value) and value>=0 else None
        except (TypeError,ValueError,OverflowError):return None
    liq=market_value('liquidity_usd')
    vol=market_value('volume_24h_usd')
    issues=[]
    if liq is None:issues.append('liquidità non disponibile')
    elif liq<MIN_LIQUIDITY:issues.append('liquidità inferiore a $1000')
    if vol is None:issues.append('volume 24h non disponibile')
    elif vol<MIN_VOLUME_24H:issues.append('volume 24h inferiore a $1000')
    warning=' · '.join(issues) if issues else 'dati mercato disponibili'
    warning+=' · vendibilità NON verificata'
    symbol=str(quote.get('symbol') or '?')[:24]
    timestamp=int(time.time()) if now is None else int(now)
    initialize(c)
    pos=c.execute('SELECT * FROM meme_demo_positions WHERE address=?',(address,)).fetchone()
    cash=float(c.execute('SELECT cash_usd FROM meme_demo_account WHERE id=1').fetchone()[0])
    if action=='BUY':
        if pos is not None:raise ValueError('Test già aperto su questo token')
        n=c.execute('SELECT COUNT(*) FROM meme_demo_positions').fetchone()[0]
        if n>=MAX_POSITIONS:raise ValueError('Massimo tre test aperti')
        if cash+1e-9<STAKE_USD:raise ValueError('Crediti demo insufficienti')
        qty=STAKE_USD/(price*(1+BUY_COST))
        with c:
            c.execute('UPDATE meme_demo_account SET cash_usd=cash_usd-? WHERE id=1',(STAKE_USD,))
            c.execute('INSERT INTO meme_demo_positions VALUES(?,?,?,?,?,?,?,?)',
                      (address,symbol,qty,price,STAKE_USD,timestamp,price,timestamp))
            c.execute('INSERT INTO meme_demo_trades(timestamp,address,symbol,action,quantity,price_usd,cost_usd,pnl_usd,note) VALUES(?,?,?,?,?,?,?,?,?)',
                      (timestamp,address,symbol,'BUY',qty,price,STAKE_USD,None,
                       'Ingresso manuale · prezzo indicativo USD · 3% costo modellato · '+warning))
        return {'ok':True,'action':'BUY','mode':'DEMO_USD_PAPER','cost_usd':STAKE_USD,'warnings':issues}
    if pos is None:raise ValueError('Nessun test aperto per questo token')
    proceeds=float(pos['quantity'])*price*(1-SELL_COST)
    pnl=proceeds-float(pos['cost_usd'])
    with c:
        c.execute('UPDATE meme_demo_account SET cash_usd=cash_usd+? WHERE id=1',(proceeds,))
        c.execute('DELETE FROM meme_demo_positions WHERE address=?',(address,))
        c.execute('INSERT INTO meme_demo_trades(timestamp,address,symbol,action,quantity,price_usd,cost_usd,pnl_usd,note) VALUES(?,?,?,?,?,?,?,?,?)',
                  (timestamp,address,pos['symbol'],'SELL',pos['quantity'],price,proceeds,pnl,
                   'Uscita manuale DEMO · prezzo indicativo USD · 3% costo modellato · '+warning))
    return {'ok':True,'action':'SELL','mode':'DEMO_USD_PAPER','pnl_usd':round(pnl,6),
            'proceeds_usd':round(proceeds,6),'warnings':issues}
