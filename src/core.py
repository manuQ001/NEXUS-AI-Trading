"""NEXUS paper-only trading core. No real-order functions or credentials."""
import json, math, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'nexus.sqlite3'
SYMBOLS = {'BTC':'XBTEUR','ETH':'ETHEUR'}
START = {'core':105.0,'meme':45.0}
FEE = .0025
SLIPPAGE = .0005
RISK_PER_TRADE = .005
DAILY_MAX = .02
POSITION_FRACTION = .25
AGENTS = ['HEAD OF DESK','SEARCH','RISK','SNIPER','WHALE','RUG','EXIT','SHILL']


def connect(db=None):
    c = sqlite3.connect(str(db or DB))
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS wallets(strategy TEXT PRIMARY KEY, cash REAL NOT NULL, initial REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY, strategy TEXT NOT NULL, qty REAL NOT NULL, entry REAL NOT NULL, stop REAL NOT NULL, target REAL NOT NULL, entry_fee REAL NOT NULL, opened_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, symbol TEXT, action TEXT, qty REAL, price REAL, fee REAL, pnl REAL, details TEXT);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, agent TEXT, level TEXT, message TEXT);
    CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER, candle_time INTEGER, symbol TEXT, outcome TEXT, reason TEXT);
    CREATE TABLE IF NOT EXISTS market_history(symbol TEXT NOT NULL, candle_time INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL, PRIMARY KEY(symbol,candle_time));
    ''')
    for k, v in START.items():
        c.execute('INSERT OR IGNORE INTO wallets VALUES(?,?,?)',(k,v,v))
    c.commit()
    return c


def emit(c, agent, message, level='info'):
    c.execute('INSERT INTO events(timestamp,agent,level,message) VALUES(?,?,?,?)',(int(time.time()),agent,level,message))


def state(c, key, default=None):
    row=c.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
    return json.loads(row['value']) if row else default


def put(c,key,value):
    c.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))


def fetch_kraken(symbol, interval=5):
    pair = SYMBOLS[symbol]
    url=f'https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}'
    req=Request(url,headers={'User-Agent':'NEXUS-Paper-Only/2.0'})
    with urlopen(req,timeout=12) as response:
        obj=json.load(response)
    if obj.get('error'):
        raise ValueError('Kraken: '+str(obj['error']))
    raw=next(v for k,v in obj['result'].items() if k!='last')
    candles=[{'time':int(x[0]),'open':float(x[1]),'high':float(x[2]),'low':float(x[3]),'close':float(x[4]),'volume':float(x[6])} for x in raw]
    # Kraken explicitly includes a running, uncommitted last candle.
    return candles[:-1]


def store_closed_candles(c, symbol, candles):
    """Archive Kraken's closed candles; idempotent and never creates orders."""
    if symbol not in SYMBOLS:
        raise ValueError('Simbolo non valido')
    rows=[]
    for x in candles:
        t=int(x['time'])
        o,h,l,cl,v=(float(x[k]) for k in ('open','high','low','close','volume'))
        if (t<=0 or not all(math.isfinite(z) for z in (o,h,l,cl,v))
                or min(o,h,l,cl)<=0 or v<0 or l>min(o,cl) or h<max(o,cl)):
            raise ValueError('Candela OHLCV non valida')
        rows.append((symbol,t,o,h,l,cl,v))
    c.executemany('INSERT OR IGNORE INTO market_history(symbol,candle_time,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?)',rows)
    # Retain the newest 200,000 candles per market (~1.9 years at 5m).
    c.execute('''DELETE FROM market_history WHERE symbol=? AND candle_time <
        COALESCE((SELECT candle_time FROM market_history WHERE symbol=?
        ORDER BY candle_time DESC LIMIT 1 OFFSET 199999),0)''',(symbol,symbol))
    return len(rows)


def load_closed_history(c, symbol, limit=100000):
    if symbol not in SYMBOLS: raise ValueError('Simbolo non valido')
    if not isinstance(limit,int) or not 1<=limit<=200000: raise ValueError('Limite non valido')
    rows=c.execute('''SELECT candle_time,open,high,low,close,volume
        FROM market_history WHERE symbol=? ORDER BY candle_time DESC LIMIT ?''',(symbol,limit)).fetchall()
    return [{'time':r['candle_time'],'open':r['open'],'high':r['high'],
             'low':r['low'],'close':r['close'],'volume':r['volume']} for r in reversed(rows)]


def historical_coverage(c, symbol):
    x=c.execute('SELECT COUNT(*) AS n, MIN(candle_time) AS first, MAX(candle_time) AS last FROM market_history WHERE symbol=?',(symbol,)).fetchone()
    return {'symbol':symbol,'candles':x['n'],'first':x['first'],'last':x['last'],
            'span_days':round((x['last']-x['first'])/86400,2) if x['first'] is not None else 0,
            'note':'Archivio locale di sole candele chiuse; non recupera automaticamente periodi anteriori ai dati Kraken disponibili.'}


def ema(values, n):
    if len(values)<n: return None
    a=2/(n+1)
    avg=sum(values[:n])/n
    for v in values[n:]: avg=avg+a*(v-avg)
    return avg


def rsi(values, n=14):
    if len(values)<=n: return None
    gains=[max(0,values[i]-values[i-1]) for i in range(1,len(values))]
    losses=[max(0,values[i-1]-values[i]) for i in range(1,len(values))]
    g=sum(gains[:n])/n; l=sum(losses[:n])/n
    for i in range(n,len(gains)):
        g=(g*(n-1)+gains[i])/n; l=(l*(n-1)+losses[i])/n
    return 100 if l==0 else 100-100/(1+g/l)


def atr(candles,n=14):
    if len(candles)<n+1: return None
    trs=[]
    for i in range(1,len(candles)):
        x=candles[i]; p=candles[i-1]['close']
        trs.append(max(x['high']-x['low'],abs(x['high']-p),abs(x['low']-p)))
    avg=sum(trs[:n])/n
    for t in trs[n:]:avg=(avg*(n-1)+t)/n
    return avg


def signal(candles):
    if len(candles)<35:return {'buy':False,'why':'Dati insufficienti'}
    closes=[v['close'] for v in candles]
    fast=ema(closes,9); slow=ema(closes,21); momentum=rsi(closes); volatility=atr(candles)
    previous_fast=ema(closes[:-1],9); previous_slow=ema(closes[:-1],21)
    cross=previous_fast<=previous_slow and fast>slow
    is_buy=bool(cross and 45<=momentum<=70 and volatility>0)
    return {'buy':is_buy,'why':('Incrocio EMA 9/21 con filtro RSI' if is_buy else 'Nessun ingresso secondo EMA 9/21 + RSI'),
            'ema9':fast,'ema21':slow,'rsi':momentum,'atr':volatility}


def wallet_status(c, prices):
    wallets=[]
    for w in c.execute('SELECT * FROM wallets').fetchall():
        ps=c.execute('SELECT * FROM positions WHERE strategy=?',(w['strategy'],)).fetchall()
        mark=sum(p['qty']*prices.get(p['symbol'],p['entry']) for p in ps)
        equity=w['cash']+mark
        wallets.append({'strategy':w['strategy'],'cash':round(w['cash'],4),'equity':round(equity,4),'initial':w['initial'],'pnl':round(equity-w['initial'],4)})
    return wallets


def daily_loss(c):
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    start=int(datetime.strptime(today,'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
    value=c.execute('SELECT COALESCE(SUM(pnl),0) FROM trades WHERE action="SELL" AND timestamp>=?',(start,)).fetchone()[0]
    return float(value)


def try_buy(c,symbol,candles,indicator):
    if not indicator['buy']: return
    if c.execute('SELECT 1 FROM positions LIMIT 1').fetchone():
        emit(c,'RISK',f'{symbol}: ingresso bloccato: già presente una posizione');return
    if daily_loss(c)<=-sum(START.values())*DAILY_MAX:
        emit(c,'RISK','Limite giornaliero di perdita raggiunto','warning');return
    cash=c.execute('SELECT cash FROM wallets WHERE strategy="core"').fetchone()[0]
    last=candles[-1]; price=last['close']*(1+SLIPPAGE)
    distance=max(indicator['atr']*1.5,price*.003)
    risk_euro=sum(START.values())*RISK_PER_TRADE
    qty=min(risk_euro/distance,(cash*POSITION_FRACTION)/(price*(1+FEE)))
    if qty<=0 or qty*price<5:
        emit(c,'RISK',f'{symbol}: importo insufficiente per un trade prudente');return
    fee=qty*price*FEE
    c.execute('UPDATE wallets SET cash=cash-? WHERE strategy="core"',(qty*price+fee,))
    c.execute('INSERT INTO positions VALUES(?,?,?,?,?,?,?,?)',(symbol,'core',qty,price,price-distance,price+distance*2,fee,int(time.time())))
    c.execute('INSERT INTO trades(timestamp,symbol,action,qty,price,fee,pnl,details) VALUES(?,?,?,?,?,?,?,?)',(int(time.time()),symbol,'BUY',qty,price,fee,0,indicator['why']))
    emit(c,'SNIPER',f'{symbol}: acquisto VIRTUALE {qty:.6f} a €{price:.2f}; stop €{price-distance:.2f}')


def handle_exit(c,symbol,candle):
    p=c.execute('SELECT * FROM positions WHERE symbol=?',(symbol,)).fetchone()
    if not p: return
    # Conservative intrabar priority: if both stop and target were touched, stop first.
    if candle['low']<=p['stop']:
        ref=min(p['stop'],candle['open']);reason='Stop loss'
    elif candle['high']>=p['target']:
        ref=p['target'];reason='Take profit'
    else: return
    price=ref*(1-SLIPPAGE);gross=p['qty']*price;fee=gross*FEE
    pnl=p['qty']*(price-p['entry'])-fee-p['entry_fee']
    c.execute('UPDATE wallets SET cash=cash+? WHERE strategy="core"',(gross-fee,))
    c.execute('DELETE FROM positions WHERE symbol=?',(symbol,))
    c.execute('INSERT INTO trades(timestamp,symbol,action,qty,price,fee,pnl,details) VALUES(?,?,?,?,?,?,?,?)',(int(time.time()),symbol,'SELL',p['qty'],price,fee,pnl,reason))
    emit(c,'EXIT',f'{symbol}: {reason} virtuale, P/L €{pnl:+.2f}', 'warning' if pnl<0 else 'info')


def record_decision(c,symbol,candle_time,outcome,reason):
    c.execute('INSERT INTO decisions(timestamp,candle_time,symbol,outcome,reason) VALUES(?,?,?,?,?)',(int(time.time()),candle_time,symbol,outcome,reason))

def process_candles(c,symbol,candles):
    if not candles:return {'error':'Nessuna candela ricevuta'}
    last=candles[-1]; last_key=f'last_closed_{symbol}'
    prev=state(c,last_key)
    prices=state(c,'prices',{})
    prices[symbol]=last['close'];put(c,'prices',prices)
    ind=signal(candles)
    put(c,'indicator_'+symbol,ind)
    if prev is None:
        # No historical fills: first arrival is an observation, not a trade.
        put(c,last_key,last['time'])
        emit(c,'SEARCH',f'{symbol}: feed connesso, prima candela chiusa osservata; nessun trade retroattivo')
        return ind
    if last['time']<=prev:return ind
    if last['time']-prev>10*60:
        emit(c,'RISK',f'{symbol}: feed non continuo, nessun ingresso sulla candela corrente','warning')
        record_decision(c,symbol,last['time'],'BLOCK','Feed discontinuo')
        put(c,last_key,last['time']);return ind
    put(c,last_key,last['time'])
    emit(c,'SEARCH',f'{symbol}: nuova candela chiusa, RSI {ind.get("rsi") or 0:.1f}')
    emit(c,'WHALE','Monitoraggio wallet non configurato: nessun dato whale utilizzato')
    emit(c,'SHILL','Analisi social non configurata: nessun sentiment utilizzato')
    handle_exit(c,symbol,last)
    if not ind['buy']:
        record_decision(c,symbol,last['time'],'WAIT',ind['why'])
        emit(c,'HEAD OF DESK',f'{symbol}: NESSUN TRADE — {ind["why"]}; attendo nuove condizioni')
    if ind['buy']:
        had_position=bool(c.execute('SELECT 1 FROM positions LIMIT 1').fetchone())
        emit(c,'HEAD OF DESK',f'{symbol}: segnale rilevato, richiesta autorizzazione RISK')
        emit(c,'RISK',f'{symbol}: limite 0,5% rischio teorico/trade; ordine subordinato ai controlli')
        try_buy(c,symbol,candles,ind)
        opened=bool(c.execute('SELECT 1 FROM positions WHERE symbol=?',(symbol,)).fetchone())
        record_decision(c,symbol,last['time'],'BLOCK' if had_position or not opened else 'BUY', 'Posizione esistente o veto RISK' if had_position or not opened else ind['why'])
    return ind


def startup_events(c):
    if state(c,'initialized'):return
    emit(c,'HEAD OF DESK','NEXUS avviato in modalità PAPER ONLY; nessun ordine reale disponibile')
    emit(c,'RUG','Memecoin in sola osservazione: controlli on-chain incompleti, esecuzione vietata','warning')
    emit(c,'RISK','Capitale virtuale €150: €105 Core / €45 Meme; nessuna leva')
    put(c,'initialized',True);c.commit()


def snapshot(c):
    prices=state(c,'prices',{})
    return {'wallets':wallet_status(c,prices),'prices':prices,
            'positions':[dict(r) for r in c.execute('SELECT * FROM positions')],
            'trades':[dict(r) for r in c.execute('SELECT * FROM trades ORDER BY id DESC LIMIT 80')],
            'events':[dict(r) for r in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 90')],
            'decisions':[dict(r) for r in c.execute('SELECT * FROM decisions ORDER BY id DESC LIMIT 60')],
            'indicators':{s:state(c,'indicator_'+s,{}) for s in SYMBOLS},
            'candles':{s:state(c,'candles_'+s,[]) for s in SYMBOLS},
            'updated_at':state(c,'last_update'), 'source':'Kraken EUR, candele chiuse',
            'mode':'PAPER ONLY','meme_execution':'BLOCKED: on-chain risk validation not implemented',
            'status':state(c,'feed_status',{})}


def refresh(c):
    status={}
    for symbol in SYMBOLS:
        try:
            candles=fetch_kraken(symbol)
            store_closed_candles(c,symbol,candles)
            put(c,'candles_'+symbol,candles[-80:])
            process_candles(c,symbol,candles)
            status[symbol]='OK'
        except Exception as exc:
            status[symbol]=str(exc)[:180]
            emit(c,'SEARCH',f'{symbol}: dati non disponibili, nessuna operazione: {exc}','warning')
    put(c,'feed_status',status);put(c,'last_update',int(time.time()));c.commit()
    return status
