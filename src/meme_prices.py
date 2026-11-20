"""NEXUS 3.8 Market Pulse: server-observed public REST prices, no fake ticks.

No independent market streaming prices, wallet calls, paid feeds or execution.
Each distinct price snapshot has a server observation time (not provider trade
time). This table is diagnostic and never authorizes a BUY/SELL.
"""
import math
import time
from meme_scout import ADDRESS

MAX_POINTS=900
RETENTION_SECONDS=86400
MAX_TOKENS=10
MAX_SERIES=36

def _positive(value):
    try:
        num=float(value)
        return num if math.isfinite(num) and num>0 else None
    except (TypeError,ValueError,OverflowError):
        return None

def _nonnegative(value):
    try:
        num=float(value)
        return num if math.isfinite(num) and num>=0 else None
    except (TypeError,ValueError,OverflowError):
        return None

def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS meme_quote_latest(
        address TEXT PRIMARY KEY, symbol TEXT NOT NULL,
        source TEXT NOT NULL,price_usd REAL NOT NULL,
        observed_at INTEGER NOT NULL, liquidity_usd REAL,
        volume_24h_usd REAL, change_id INTEGER NOT NULL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS meme_quote_changes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,address TEXT NOT NULL,
        observed_at INTEGER NOT NULL, price_usd REAL NOT NULL,
        source TEXT NOT NULL)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_quote_changes_address
        ON meme_quote_changes(address,id)""")

def observe(c,address,quote,now=None,source='DEX_SCREENER_REST'):
    """Only record genuine, validated provider quotes. No synthetic interpolation.

    A repeated price refreshes last-observed time but does not produce a
    fabricated price-change event. Return change ID only if price changed.
    """
    if not isinstance(address,str) or not ADDRESS.fullmatch(address):
        return None
    if not isinstance(quote,dict):
        return None
    price=_positive(quote.get('price_usd'))
    if not price:return None
    now=int(time.time()) if now is None else int(now)
    if now<0:return None
    if source!='DEX_SCREENER_REST':return None
    initialize(c)
    symbol=str(quote.get('symbol') or '?')[:24]
    liquidity=_nonnegative(quote.get('liquidity_usd'))
    volume=_nonnegative(quote.get('volume_24h_usd'))
    previous=c.execute('SELECT price_usd,observed_at,change_id FROM meme_quote_latest WHERE address=?',
                       (address,)).fetchone()
    # Ignore delayed observations rather than rolling history and freshness back.
    if previous is not None and now<int(previous['observed_at']):
        return None
    changed=previous is None or price!=float(previous['price_usd'])
    change_id=int(previous['change_id']) if previous else 0
    if changed:
        c.execute('INSERT INTO meme_quote_changes(address,observed_at,price_usd,source) VALUES(?,?,?,?)',
                  (address,now,price,source))
        change_id=int(c.execute('SELECT last_insert_rowid()').fetchone()[0])
    c.execute("""INSERT INTO meme_quote_latest(
        address,symbol,source,price_usd,observed_at,liquidity_usd,
        volume_24h_usd,change_id) VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(address) DO UPDATE SET symbol=excluded.symbol,
        source=excluded.source,price_usd=excluded.price_usd,
        observed_at=excluded.observed_at,liquidity_usd=excluded.liquidity_usd,
        volume_24h_usd=excluded.volume_24h_usd,
        change_id=excluded.change_id""",
        (address,symbol,source,price,now,liquidity,volume,change_id))
    # Keep bounded in SQLite even after days of unattended operation.
    c.execute('DELETE FROM meme_quote_changes WHERE observed_at<?',(now-RETENTION_SECONDS,))
    c.execute('DELETE FROM meme_quote_latest WHERE observed_at<?',(now-RETENTION_SECONDS,))
    c.execute("""DELETE FROM meme_quote_changes WHERE id NOT IN
        (SELECT id FROM meme_quote_changes ORDER BY id DESC LIMIT ?)""",
        (MAX_POINTS,))
    c.execute("""DELETE FROM meme_quote_latest WHERE address NOT IN
        (SELECT address FROM meme_quote_latest ORDER BY observed_at DESC,address LIMIT ?)""",
        (MAX_POINTS,))
    return change_id if changed else None

WATCH_INTERVAL_SECONDS=10
WATCH_RECENT_SECONDS=600
WATCH_MAX_TOKENS=3

def monitor_initialize(c):
    initialize(c)
    c.execute("""CREATE TABLE IF NOT EXISTS meme_quote_monitor(
        id INTEGER PRIMARY KEY CHECK(id=1),
        last_attempt INTEGER NOT NULL DEFAULT 0,
        last_success INTEGER NOT NULL DEFAULT 0,
        checked INTEGER NOT NULL DEFAULT 0,
        errors INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '')""")
    c.execute("INSERT OR IGNORE INTO meme_quote_monitor(id) VALUES(1)")

def refresh_watchlist(c,now=None,quote=None):
    """Poll at most 3 recently observed tokens, even with no open PAPER positions.

    These read-only reference quotes never pass into the execution engine.
    Only server-side public REST calls are allowed. No paid WS subscriptions,
    fake price ticks, or bypass of the persistent drawdown lock.
    """
    monitor_initialize(c)
    now=int(time.time()) if now is None else int(now)
    state=c.execute('SELECT last_attempt FROM meme_quote_monitor WHERE id=1').fetchone()
    if now-int(state['last_attempt'])<WATCH_INTERVAL_SECONDS:
        return {'status':'RATE_LIMITED','checked':0,'errors':0}
    # No market monitoring after the user explicitly suspends MEME AUTO.
    a=c.execute("SELECT enabled FROM meme_auto_state WHERE id=1").fetchone()
    if not a or not a['enabled']:
        return {'status':'AUTO_SUSPENDED','checked':0,'errors':0}
    # Watch only recently discovered tokens with sufficiently useful public
    # market quality, prioritizing liquid candidates over feed noise.
    positions={r['address'] for r in c.execute('SELECT address FROM meme_eur_positions')}
    rows=c.execute("""SELECT address FROM meme_quote_latest
        WHERE observed_at>=? AND liquidity_usd>=10000 AND volume_24h_usd>=20000
        ORDER BY liquidity_usd DESC,volume_24h_usd DESC,address LIMIT 20""",
        (now-WATCH_RECENT_SECONDS,)).fetchall()
    addresses=[row['address'] for row in rows if row['address'] not in positions][:WATCH_MAX_TOKENS]
    checked=0
    errors=0
    last_error=''
    from meme_demo import indicative_quote
    obtain=quote if quote is not None else indicative_quote
    for address in addresses:
        try:
            q=obtain(address)
            if not isinstance(q,dict) or not _positive(q.get('price_usd')):
                raise ValueError('Invalid quote')
            observe(c,address,q,now=now)
            checked+=1
        except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
            errors+=1
            last_error=type(exc).__name__
    c.execute("""UPDATE meme_quote_monitor
        SET last_attempt=?,last_success=CASE WHEN ?>0 THEN ? ELSE last_success END,
        checked=?,errors=?,last_error=? WHERE id=1""",
        (now,checked,now,checked,errors,last_error))
    return {'status':'OBSERVED' if checked else 'NO_VALID_QUOTES',
            'checked':checked,'errors':errors}

def changes_after(c,last_id=0,limit=25):
    initialize(c)
    try:last_id=max(0,int(last_id))
    except (ValueError,TypeError):last_id=0
    limit=max(1,min(40,int(limit)))
    return [dict(x) for x in c.execute("""SELECT c.id,c.address,c.observed_at,
          c.price_usd,c.source,l.symbol FROM meme_quote_changes c
          LEFT JOIN meme_quote_latest l ON l.address=c.address
          WHERE c.id>? ORDER BY c.id LIMIT ?""",(last_id,limit))]

def snapshot(c,now=None):
    initialize(c)
    now=int(time.time()) if now is None else int(now)
    from meme_auto import status
    from meme_demo import BUY_COST,SELL_COST
    auto=status(c)
    risk=auto.get('risk_circuit',{})
    result=[]
    rows=c.execute("""SELECT * FROM meme_quote_latest
        ORDER BY observed_at DESC,address LIMIT ?""",(MAX_TOKENS,)).fetchall()
    for row in rows:
        d=dict(row)
        points=[{'time':int(p['observed_at']),'price_usd':float(p['price_usd'])}
                for p in reversed(c.execute("""SELECT observed_at,price_usd
                     FROM meme_quote_changes WHERE address=? ORDER BY id DESC LIMIT ?""",
                     (d['address'],MAX_SERIES)).fetchall())]
        age=max(0,now-int(d['observed_at']))
        result.append({'address':d['address'],'symbol':d['symbol'],
            'source':d['source'],'price_usd':d['price_usd'],
            'liquidity_usd':d['liquidity_usd'],
            'volume_24h_usd':d['volume_24h_usd'],
            'observed_at':d['observed_at'],'age_seconds':age,
            'fresh':age<=45,'observations':points})
    round_trip_break_even=(1+BUY_COST)/(1-SELL_COST)-1
    gross_for_net_target=(1+0.12)*(1+BUY_COST)/(1-SELL_COST)-1
    net_at_gross_stop=(1-0.05)*(1-SELL_COST)/(1+BUY_COST)-1
    monitor_initialize(c)
    monitor_row=dict(c.execute('SELECT * FROM meme_quote_monitor WHERE id=1').fetchone())
    return {'mode':'OBSERVED_REST_PRICES','quotes':result,
            'monitor':{'interval_seconds':WATCH_INTERVAL_SECONDS,
                'last_attempt':monitor_row['last_attempt'],
                'last_success':monitor_row['last_success'],
                'checked':monitor_row['checked'],
                'errors':monitor_row['errors'],
                'last_error':monitor_row['last_error']},
            'cost_model':{'buy_pct':BUY_COST*100,'sell_pct':SELL_COST*100,
               'minimum_gross_move_to_break_even_pct':round(round_trip_break_even*100,3),
               'gross_move_for_net_target_12_pct':round(gross_for_net_target*100,3),
               'estimated_net_at_gross_stop_minus5_pct':round(net_at_gross_stop*100,3)},
            'sample_count':c.execute('SELECT COUNT(*) FROM meme_quote_changes').fetchone()[0],
            'last_change_id':c.execute('SELECT COALESCE(MAX(id),0) FROM meme_quote_changes').fetchone()[0],
            'risk':risk,
            'disclaimer':('Quotazioni DEX Screener REST osservate dal server. '
              'Ogni punto e un valore effettivamente letto, non un tick di transazione. '
              'Nessuna interpolazione, nessuna garanzia di prezzo eseguibile. '
              'Non si modifica il portafoglio o il Risk Lock.')}
