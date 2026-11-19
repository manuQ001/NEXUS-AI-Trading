"""Transparent, read-only multi-agent research protocol.

No external AI API, no real orders and no wallet mutations. Independent
advisory opinions are not authorization to trade.
"""
from datetime import datetime, timezone
import math

AGENT_NAMES=('SEARCH','HEAD OF DESK','RISK','SNIPER','EXIT','WHALE','RUG','SHILL')


def review(symbol, candles, indicator, *, positions=(), daily_realized=0.0,
           initial_capital=150.0, max_daily_loss=0.02, feed_ok=True):
    """Return a structured report on the latest closed candle.

    RISK is a hard veto. WHALE/SHILL are explicitly unavailable until real
    trusted data adapters exist; no fictional intelligence is produced.
    """
    if symbol not in ('BTC','ETH'):
        raise ValueError('Simbolo non supportato')
    if not candles:
        raise ValueError('Nessuna candela chiusa')
    if not isinstance(indicator,dict):
        raise ValueError('Indicatori non validi')
    candle=candles[-1]
    price=float(candle['close'])
    if not math.isfinite(price) or price<=0:
        raise ValueError('Prezzo non valido')
    blocked=[]
    if not feed_ok: blocked.append('Feed non affidabile')
    if len(candles)<70: blocked.append('Storico insufficiente')
    if not math.isfinite(float(daily_realized)): blocked.append('PnL giornaliero non valido')
    elif daily_realized<=-initial_capital*max_daily_loss: blocked.append('Limite perdite giornaliere')
    if positions: blocked.append('Posizione già aperta')
    buy=indicator.get('buy') is True
    if not isinstance(indicator.get('atr'),(int,float)) or not math.isfinite(indicator.get('atr',0)) or indicator.get('atr',0)<=0:
        if buy:blocked.append('Volatilità non validata')
    risk_ok=not blocked
    proposal='BUY' if buy else 'WAIT'
    approved=buy and risk_ok
    report=[
        ('SEARCH','signal' if buy else 'wait',indicator.get('why','Segnale non disponibile')),
        ('HEAD OF DESK','paper_buy_candidate' if approved else ('veto' if buy else 'wait'),
         'Candidato PAPER soltanto: soggetto a verifica RISK' if approved else ('Veto RISK' if buy else 'Nessun ingresso proposto')),
        ('RISK','approved' if risk_ok else 'blocked',', '.join(blocked) if blocked else 'Limiti preliminari rispettati'),
        ('SNIPER','paper_ready' if approved else 'idle','Nessun ordine inviato dal protocollo di analisi'),
        ('EXIT','monitor' if positions else 'idle','Uscite gestite separatamente da stop e target nel motore paper'),
        ('WHALE','unavailable','Dati wallet non collegati: nessuna analisi whale'),
        ('RUG','meme_blocked','Memecoin disabilitate finché non esistono controlli on-chain validati'),
        ('SHILL','unavailable','Dati social non collegati: nessuna analisi sentiment'),
    ]
    return {'symbol':symbol,'time':int(candle['time']),'proposal':proposal,
            'paper_candidate':approved,'risk_veto':not risk_ok,
            'agents':[{'name':name,'status':status,'reason':reason} for name,status,reason in report],
            'mode':'READ ONLY / PAPER ONLY',
            'note':'Opinioni a regole, non agenti LLM. La decisione non esegue ordini e non scavalca try_buy.'}
