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
