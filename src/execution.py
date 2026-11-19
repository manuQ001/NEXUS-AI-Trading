"""Shared execution-cost primitives for PAPER and historical simulations.

Not an exchange connector. Prices are indicative reference points; a real
market order can execute at a different price or fail to fill.
"""
import math


def _positive_finite(value, label):
    try:
        number=float(value)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError(label+' non valido') from exc
    if not math.isfinite(number) or number<=0:
        raise ValueError(label+' non valido')
    return number


def _rate(value, label):
    try:
        number=float(value)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError(label+' non valido') from exc
    if not math.isfinite(number) or not 0<=number<1:
        raise ValueError(label+' non valido')
    return number


def execution_price(side, reference_price, slippage_rate):
    """BUY pays more, SELL receives less. No prediction of actual liquidity."""
    price=_positive_finite(reference_price,'Prezzo')
    slip=_rate(slippage_rate,'Slippage')
    if side=='BUY':
        return price*(1+slip)
    if side=='SELL':
        return price*(1-slip)
    raise ValueError('Lato ordine non valido')


def execution_fee(quantity, price, fee_rate):
    """Fee on traded notional, not on profit."""
    quantity=_positive_finite(quantity,'Quantità')
    price=_positive_finite(price,'Prezzo')
    fee=_rate(fee_rate,'Commissione')
    return quantity*price*fee


def sell_settlement(quantity, entry_price, entry_fee, exit_reference, *,
                    fee_rate, slippage_rate):
    """Return net SELL proceeds and closed-trade P/L including both sides."""
    quantity=_positive_finite(quantity,'Quantità')
    entry=_positive_finite(entry_price,'Prezzo di ingresso')
    entry_fee=float(entry_fee)
    if not math.isfinite(entry_fee) or entry_fee<0:
        raise ValueError('Commissione di ingresso non valida')
    exit_price=execution_price('SELL',exit_reference,slippage_rate)
    gross=quantity*exit_price
    exit_fee=execution_fee(quantity,exit_price,fee_rate)
    net=gross-exit_fee
    pnl=net-quantity*entry-entry_fee
    return {'price':exit_price,'gross':gross,'exit_fee':exit_fee,
            'net_proceeds':net,'pnl':pnl}


def hypothetical_partial_fill(side, requested_quantity, midpoint, available_quantity, *,
                              participation_rate=0.05, spread_bps=5,
                              slippage_bps=5, latency_bps=0, fee_rate=0.0025):
    """Synthetic liquidity stress test, NOT live execution or an exchange fill.

    All inputs are caller-provided scenario assumptions. `available_quantity`
    is accessible opposing-side liquidity in base units, not candle volume.
    `latency_bps` is an assumed adverse price movement during a delay, NOT
    a measured latency. No liquidity supplied -> no fill.
    """
    if side not in ('BUY','SELL'):
        raise ValueError('Lato non valido')
    requested=_positive_finite(requested_quantity,'Quantità richiesta')
    mid=_positive_finite(midpoint,'Prezzo centrale')
    try:
        available=float(available_quantity)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError('Liquidità disponibile non valida') from exc
    if not math.isfinite(available) or available<0:
        raise ValueError('Liquidità disponibile non valida')
    participation=_rate(participation_rate,'Partecipazione')
    if participation<=0:
        raise ValueError('Partecipazione nulla')
    rates=[]
    for name,value in (('Spread bps',spread_bps),('Slippage bps',slippage_bps),
                       ('Movimento durante ritardo bps',latency_bps)):
        try: rate=float(value)
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError(name+' non valido') from exc
        if not math.isfinite(rate) or not 0<=rate<10000:
            raise ValueError(name+' non valido')
        rates.append(rate)
    spread,slip,lag=rates
    fee=_rate(fee_rate,'Commissione')
    fill_qty=min(requested,available*participation)
    remaining=max(0.0,requested-fill_qty)
    if fill_qty<=0:
        return {'status':'NO_FILL','requested_qty':requested,'filled_qty':0.0,
                'unfilled_qty':requested,'price':None,'fee':0.0,'gross':0.0,
                'mode':'SYNTHETIC SCENARIO ONLY'}
    # midpoint -> adverse half-spread -> adverse slippage/latency shift.
    adverse=(spread/2+slip+lag)/10000
    price=mid*(1+adverse) if side=='BUY' else mid*(1-adverse)
    gross=fill_qty*price
    return {'status':'FILLED' if remaining<=1e-12 else 'PARTIAL',
            'requested_qty':requested,'filled_qty':fill_qty,
            'unfilled_qty':remaining,'price':price,'fee':gross*fee,
            'gross':gross,'mode':'SYNTHETIC SCENARIO ONLY'}


def execution_stress_scenarios(midpoint, order_eur=25.0):
    """Read-only examples with invented depth/price-impact assumptions.

    These are deliberately NOT inferred from Kraken candles or order book.
    """
    mid=_positive_finite(midpoint,'Prezzo di riferimento')
    amount=_positive_finite(order_eur,'Importo ordine')
    if amount>1000000:
        raise ValueError('Importo simulato troppo grande')
    quantity=amount/mid
    cases=(
        ('Liquidità abbondante',2000.0,4.0,5.0,2.0),
        ('Liquidità moderata',100.0,12.0,10.0,10.0),
        ('Liquidità scarsa',20.0,40.0,35.0,40.0),
    )
    results=[]
    for label,depth_eur,spread,slip,lag in cases:
        report=hypothetical_partial_fill(
            'BUY',quantity,mid,depth_eur/mid,participation_rate=.25,
            spread_bps=spread,slippage_bps=slip,latency_bps=lag)
        results.append({'scenario':label,'assumed_depth_eur':depth_eur,
                        'assumed_spread_bps':spread,
                        'assumed_slippage_bps':slip,
                        'assumed_delay_impact_bps':lag,
                        'filled_eur':round(report['gross'],4),
                        'fee_eur':round(report['fee'],4),
                        'fill_percentage':round(100*report['filled_qty']/quantity,2),
                        'status':report['status']})
    return {'mode':'HYPOTHETICAL STUDY - NO ORDERS',
            'reference_mid_eur':mid,'requested_eur':amount,
            'participation_rate':.25,'scenarios':results,
            'warning':'Volumi, spread e impatto del ritardo sono ipotesi inventate per test, NON misure di mercato. Nessuna previsione di eseguibilità.'}


def sniper_book_preview(book, *, order_eur=25.0, participation_rate=0.10,
                        slippage_bps=5.0, delay_impact_bps=10.0,
                        fee_rate=0.0025):
    """Conservative READ-ONLY BUY study using visible Kraken asks.

    Levels are OBSERVED; participation, slippage and delay impact are
    EXPLICIT HYPOTHESES, not market measurements or guaranteed fills.
    The requested quantity is sized from the best ask with cost cushion.
    It NEVER writes to an account, places an order or clears RISK.
    """
    amount=_positive_finite(order_eur,'Budget')
    if amount>10000:
        raise ValueError('Budget di studio eccessivo')
    part=_rate(participation_rate,'Partecipazione')
    if part<=0:raise ValueError('Partecipazione nulla')
    fee=_rate(fee_rate,'Commissione')
    try:
        slip=float(slippage_bps);delay=float(delay_impact_bps)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError('Costi ipotetici non validi') from exc
    if not all(math.isfinite(x) and 0<=x<10000 for x in (slip,delay)):
        raise ValueError('Costi ipotetici non validi')
    if not isinstance(book,dict):
        raise ValueError('Book non valido')
    asks=book.get('asks')
    if not isinstance(asks,list) or not asks or len(asks)>20:
        raise ValueError('Ask non valide')
    best=_positive_finite(book.get('best_ask'),'Best ask')
    bid=_positive_finite(book.get('best_bid'),'Best bid')
    if bid>=best:
        raise ValueError('Book incrociato')
    penalty=(slip+delay)/10000
    requested=amount/(best*(1+penalty)*(1+fee))
    remaining=requested;matched=0.;gross=0.;last=0.;prev=0.
    for level in asks:
        if not isinstance(level,dict):raise ValueError('Livello non valido')
        price=_positive_finite(level.get('price'),'Prezzo')
        volume=_positive_finite(level.get('volume'),'Volume')
        if prev and price<=prev:raise ValueError('Ask non ordinate')
        if not prev and price!=best:raise ValueError('Best ask incoerente')
        prev=price
        take=min(remaining,volume*part)
        if take>0:
            matched+=take
            gross+=take*price*(1+penalty)
            last=price
        remaining=max(0.,requested-matched)
        if remaining<=requested*1e-10:break
    pct=min(100.,100*matched/requested)
    remaining=max(0.,requested-matched)
    fee_eur=gross*fee
    total=gross+fee_eur
    # Walking higher asks can consume more than the budget despite
    # sizing with the best ask. Mark that result as NOT BUDGET-SAFE.
    budget_ok=total<=amount*(1+1e-10)
    full=remaining<=requested*1e-10
    return {
        'status':'ESTIMATE_FULL' if full and budget_ok else (
            'ESTIMATE_PARTIAL' if budget_ok else 'OVER_BUDGET'),
        'order_budget_eur':amount,'requested_qty':requested,
        'estimated_filled_qty':matched,'estimated_unfilled_qty':remaining,
        'estimated_fill_pct':round(pct,4),
        'estimated_vwap_eur':gross/matched if matched else None,
        'estimated_gross_eur':gross,'estimated_fee_eur':fee_eur,
        'estimated_total_eur':total,'budget_ok':budget_ok,
        'observed_best_ask_eur':best,'observed_best_bid_eur':bid,
        'assumed_participation_pct':part*100,
        'assumed_slippage_bps':slip,'assumed_delay_impact_bps':delay,
        'fee_rate_pct':fee*100,'source':'Kraken asks snapshot',
        'mode':'READ ONLY / MIXED OBSERVED DEPTH + HYPOTHETICAL COSTS',
        'warning':'Book osservato, ma quota di partecipazione, slippage e movimento nel ritardo sono ipotesi. Nessun fill garantito, nessun ordine inviato.'
    }


def assess_exit_bar(candle, stop, target, *, allow_target=True):
    """Conservative exit resolution for a COMPLETED OHLC bar.

    With only OHLC there is no ordering of high/low inside a bar:
    if both are touched, STOP wins. Gap down through stop uses the
    bar open; favourable gap up through target is capped at target.
    When historical bars are missing, callers can disable target exits
    rather than inferring a profitable exit across an unknown interval.
    This is a pure paper/backtest decision, not a market order.
    """
    if not isinstance(candle,dict):
        raise ValueError('Candela non valida')
    opening=_positive_finite(candle.get('open'),'Open')
    high=_positive_finite(candle.get('high'),'High')
    low=_positive_finite(candle.get('low'),'Low')
    stop=_positive_finite(stop,'Stop')
    target=_positive_finite(target,'Target')
    if not low<=opening<=high or stop>=target:
        raise ValueError('Dati OHLC o soglie incoerenti')
    stop_hit=low<=stop
    target_hit=high>=target
    if stop_hit:
        raw=min(stop,opening)
        return {'reference':raw,'reason':'Stop loss',
                'ambiguous_both_touched':target_hit,
                'gap_through_stop':opening<stop,
                'target_suppressed':False,
                'evidence':'OHLC_BAR_CONSERVATIVE'}
    if target_hit and allow_target:
        return {'reference':target,'reason':'Take profit',
                'ambiguous_both_touched':False,
                'gap_through_stop':False,
                'target_suppressed':False,
                'evidence':'OHLC_BAR_CONSERVATIVE'}
    return {'reference':None,'reason':None,
            'ambiguous_both_touched':False,
            'gap_through_stop':False,
            'target_suppressed':bool(target_hit and not allow_target),
            'evidence':'OHLC_BAR_CONSERVATIVE'}


def assess_exit_ticks(ticks, opened_at, stop, target):
    """Read-only chronological tick replay, for later verified-tick research.

    Ticks must be sorted [(unix_timestamp, traded_price),...].
    This NEVER pulls real trades or mutates the paper engine.
    It rejects out-of-order observations and discards pre-entry ticks.
    Trade prints do NOT guarantee an order's executable bid/ask.
    """
    stop=_positive_finite(stop,'Stop')
    target=_positive_finite(target,'Target')
    if stop>=target:raise ValueError('Soglie incoerenti')
    if not isinstance(ticks,(list,tuple)) or len(ticks)>10000:
        raise ValueError('Tick non validi')
    try: entry=float(opened_at)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError('Ingresso non valido') from exc
    if not math.isfinite(entry) or entry<=0:raise ValueError('Ingresso non valido')
    prev=-math.inf
    for item in ticks:
        if not isinstance(item,(tuple,list)) or len(item)!=2:
            raise ValueError('Tick malformato')
        try: stamp=float(item[0])
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError('Ora tick non valida') from exc
        price=_positive_finite(item[1],'Prezzo tick')
        if not math.isfinite(stamp) or stamp<=0 or stamp<prev:
            raise ValueError('Tick non ordinati o non validi')
        prev=stamp
        if stamp<entry:continue
        if price<=stop:
            return {'reason':'Stop loss','observed_price':price,'observed_at':stamp,
                    'evidence':'TRADE_PRINT_ONLY_NOT_EXECUTABLE'}
        if price>=target:
            return {'reason':'Take profit','observed_price':price,'observed_at':stamp,
                    'evidence':'TRADE_PRINT_ONLY_NOT_EXECUTABLE'}
    return {'reason':None,'observed_price':None,'observed_at':None,
            'evidence':'TRADE_PRINT_ONLY_NOT_EXECUTABLE'}
