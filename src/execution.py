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
