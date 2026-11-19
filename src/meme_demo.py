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
    c.executescript('''
    CREATE TABLE IF NOT EXISTS meme_demo_account(
        id INTEGER PRIMARY KEY CHECK(id=1), cash_usd REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS meme_demo_positions(
        address TEXT PRIMARY KEY, symbol TEXT NOT NULL,
        quantity REAL NOT NULL, entry_price_usd REAL NOT NULL,
        cost_usd REAL NOT NULL, opened_at INTEGER NOT NULL,
        last_price_usd REAL NOT NULL, last_checked_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS meme_demo_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL,
        address TEXT NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL,
        quantity REAL NOT NULL, price_usd REAL NOT NULL,
        cost_usd REAL NOT NULL, pnl_usd REAL,
        note TEXT NOT NULL
    );
    INSERT OR IGNORE INTO meme_demo_account(id,cash_usd) VALUES(1,45.0);
    ''')
    # SQLite executescript auto-commits before execution. Do not use it
    # inside an active transaction.


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
        try:
            price=float(pair.get('priceUsd'))
            liq=float((pair.get('liquidity') or {}).get('usd'))
            vol=float((pair.get('volume') or {}).get('h24'))
        except (TypeError,ValueError,OverflowError,AttributeError):continue
        if not all(math.isfinite(x) and x>0 for x in (price,liq,vol)):continue
        eligible.append({'price_usd':price,'liquidity_usd':liq,'volume_24h_usd':vol,
                         'symbol':str(base.get('symbol') or '?')[:24]})
    if not eligible:raise ValueError('Nessun prezzo USD valido per il mint selezionato')
    return max(eligible,key=lambda q:q['liquidity_usd'])


def quick_trade(c,address,action,quote,now=None):
    """Purely local PAPER execution; caller acquires shared DB lock.
    Quote always fetched server-side, never sent from the browser.
    Requires explicit user action and realistic-ish cost stress of 3% per side.
    """
    if action not in ('BUY','SELL'):raise ValueError('Azione non autorizzata')
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):
        raise ValueError('Mint Solana non valido')
    if not isinstance(quote,dict):raise ValueError('Dati mercato mancanti')
    try:
        price=float(quote['price_usd'])
        liq=float(quote['liquidity_usd'])
        vol=float(quote['volume_24h_usd'])
    except (KeyError,TypeError,ValueError,OverflowError):raise ValueError('Prezzo non disponibile')
    if not all(math.isfinite(x) and x>0 for x in (price,liq,vol)):
        raise ValueError('Prezzo, liquidità o volume non valido')
    if liq<MIN_LIQUIDITY or vol<MIN_VOLUME_24H:
        raise ValueError('Liquidità o volume insufficiente per un test minimamente informativo')
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
                       'Ingresso manuale · prezzo indicativo USD · 3% costo modellato'))
        return {'ok':True,'action':'BUY','mode':'DEMO_USD_PAPER','cost_usd':STAKE_USD}
    if pos is None:raise ValueError('Nessun test aperto per questo token')
    proceeds=float(pos['quantity'])*price*(1-SELL_COST)
    pnl=proceeds-float(pos['cost_usd'])
    with c:
        c.execute('UPDATE meme_demo_account SET cash_usd=cash_usd+? WHERE id=1',(proceeds,))
        c.execute('DELETE FROM meme_demo_positions WHERE address=?',(address,))
        c.execute('INSERT INTO meme_demo_trades(timestamp,address,symbol,action,quantity,price_usd,cost_usd,pnl_usd,note) VALUES(?,?,?,?,?,?,?,?,?)',
                  (timestamp,address,pos['symbol'],'SELL',pos['quantity'],price,proceeds,pnl,
                   'Uscita manuale · prezzo indicativo USD · 3% costo modellato · vendibilità NON testata'))
    return {'ok':True,'action':'SELL','mode':'DEMO_USD_PAPER','pnl_usd':round(pnl,6),
            'proceeds_usd':round(proceeds,6)}
