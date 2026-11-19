"""Read-only Kraken public order-book snapshot and indicative depth walk.

No credentials, private API, trading functions or wallet access. Snapshot
liquidity is indicative; levels may disappear before an actual order.
"""
import json
import math
import time
from urllib.request import Request, urlopen

PAIRS={'BTC':'XBTEUR','ETH':'ETHEUR'}


def _positive(v, name):
    try: n=float(v)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError(name+' non valido') from exc
    if not math.isfinite(n) or n<=0:
        raise ValueError(name+' non valido')
    return n


def parse_depth(raw, symbol, *, received_at=None):
    """Validate bids/asks and return a normalized top-20 snapshot."""
    if symbol not in PAIRS:raise ValueError('Asset non supportato')
    if not isinstance(raw,dict) or raw.get('error') or not isinstance(raw.get('result'),dict):
        raise ValueError('Book Kraken non valido')
    result=raw['result']
    if len(result)!=1:raise ValueError('Risposta book ambigua')
    book=next(iter(result.values()))
    if not isinstance(book,dict):raise ValueError('Book assente')
    sides={}
    for side in ('asks','bids'):
        levels=book.get(side)
        if not isinstance(levels,list) or not levels or len(levels)>20:
            raise ValueError('Livelli '+side+' non validi')
        parsed=[]
        for level in levels:
            if not isinstance(level,(list,tuple)) or len(level)<3:
                raise ValueError('Livello '+side+' incompleto')
            price=_positive(level[0],'Prezzo')
            volume=_positive(level[1],'Volume')
            try: changed=float(level[2])
            except (TypeError,ValueError,OverflowError) as exc:
                raise ValueError('Timestamp book non valido') from exc
            if not math.isfinite(changed) or changed<=0:
                raise ValueError('Timestamp book non valido')
            parsed.append({'price':price,'volume':volume,'updated_at':changed})
        prices=[x['price'] for x in parsed]
        if len(set(prices))!=len(prices):
            raise ValueError('Prezzi duplicati')
        if prices!=sorted(prices,reverse=side=='bids'):
            raise ValueError('Livelli book non ordinati')
        sides[side]=parsed
    best_ask=sides['asks'][0]['price'];best_bid=sides['bids'][0]['price']
    if best_bid>=best_ask:raise ValueError('Book incrociato o spread non positivo')
    midpoint=(best_ask+best_bid)/2
    spread_bps=(best_ask-best_bid)/midpoint*10000
    observed=int(time.time()) if received_at is None else int(received_at)
    if observed<=0:raise ValueError('Ricezione non valida')
    return {'symbol':symbol,'observed_at':observed,'best_ask':best_ask,
            'best_bid':best_bid,'midpoint':midpoint,'spread_bps':spread_bps,
            'asks':sides['asks'],'bids':sides['bids'],
            'source':'Kraken REST Depth snapshot','authenticated':False}


def fetch_depth(symbol, count=20):
    """One bounded HTTP request per explicit user action."""
    if symbol not in PAIRS:raise ValueError('Asset non supportato')
    if type(count) is not int or not 1<=count<=20:raise ValueError('Profondità non valida')
    url=f'https://api.kraken.com/0/public/Depth?pair={PAIRS[symbol]}&count={count}'
    req=Request(url,headers={'User-Agent':'NEXUS-Paper-Only/2.0'})
    with urlopen(req,timeout=8) as res:
        payload=res.read(100000)
    raw=json.loads(payload)
    return parse_depth(raw,symbol,received_at=int(time.time()))


def walk_book(book, side, quantity, fee_rate=0.0025):
    """Compute indicative VWAP by consuming visible opposing levels.

    Unfilled quantity remains unfilled, never assume liquidity outside book.
    No market impact, race with other traders, latency, or guaranteed fills.
    """
    if side not in ('BUY','SELL'):raise ValueError('Lato non valido')
    qty=_positive(quantity,'Quantità richiesta')
    if not isinstance(book,dict):raise ValueError('Book non valido')
    try: fee=float(fee_rate)
    except (TypeError,ValueError,OverflowError) as exc:raise ValueError('Commissione non valida') from exc
    if not math.isfinite(fee) or not 0<=fee<1:raise ValueError('Commissione non valida')
    levels=book.get('asks' if side=='BUY' else 'bids')
    if not isinstance(levels,list) or not levels:raise ValueError('Livelli assenti')
    remaining=qty;cost=0.0;filled=0.0;last_price=None
    for level in levels:
        p=_positive(level['price'],'Prezzo');volume=_positive(level['volume'],'Volume')
        matched=min(remaining,volume)
        if matched<=0:break
        filled+=matched;cost+=matched*p;remaining=max(0.0,qty-filled);last_price=p
        if remaining<=1e-12:break
    if filled<=0:raise ValueError('Book privo di volume valido')
    return {'status':'INDICATIVE_FULL' if remaining<=1e-12 else 'INDICATIVE_PARTIAL',
            'requested_qty':qty,'filled_qty':filled,'unfilled_qty':remaining,
            'filled_pct':100*filled/qty,'vwap':cost/filled,
            'last_level_price':last_price,'gross_eur':cost,'estimated_fee_eur':cost*fee}


def depth_study(book, order_eur=25.0):
    """Read-only buy and sell 25 EUR equivalent; NO simulated account changes."""
    mid=_positive(book['midpoint'],'Midpoint')
    amount=_positive(order_eur,'Controvalore')
    if amount>10000:raise ValueError('Importo di studio eccessivo')
    quantity=amount/mid
    buy=walk_book(book,'BUY',quantity)
    sell=walk_book(book,'SELL',quantity)
    return {'symbol':book['symbol'],'observed_at':book['observed_at'],
            'best_ask':book['best_ask'],'best_bid':book['best_bid'],
            'spread_bps':book['spread_bps'],'midpoint':mid,
            'requested_eur':amount,'quantity_base':quantity,
            'buy':buy,'sell':sell,'mode':'READ ONLY - LIVE BOOK SNAPSHOT',
            'warning':'Liquidità visibile al momento della richiesta: non garantisce un prezzo eseguibile. Book senza misure di latenza, impatto di mercato o quote future. Nessun ordine inviato.'}
