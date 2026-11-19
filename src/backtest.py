"""Isolated, no-lookahead long-only backtest. No database writes or real orders."""
from core import signal, atr, FEE, SLIPPAGE, RISK_PER_TRADE, DAILY_MAX, POSITION_FRACTION
from datetime import datetime, timezone
import math

def test_strategy(candles, starting_cash=105.0):
    if len(candles)<70: return {'ok':False,'error':'Servono almeno 70 candele chiuse','candles':len(candles)}
    for ix, candle in enumerate(candles):
        try:
            numbers = [float(candle[k]) for k in ('open','high','low','close','volume')]
            timestamp = int(candle['time'])
            o,h,l,cl,v = numbers
            if not all(math.isfinite(n) for n in numbers) or min(o,h,l,cl)<=0 or v<0 or l>min(o,cl) or h<max(o,cl) or l>h or timestamp<=0:
                raise ValueError('OHLCV incoerente')
        except (KeyError, TypeError, ValueError, OverflowError):
            return {'ok':False,'error':f'Candela {ix}: dati OHLCV non validi'}
    for a,b in zip(candles,candles[1:]):
        if b['time']<=a['time']:return {'ok':False,'error':'Timestamp non crescenti'}
    # Indicators computed through candle i-1; next candle (i) is first tradable open.
    cash=float(starting_cash); pos=None; trades=[]; curves=[]
    initial=starting_cash; daily_realized={}; blocked=0; signals=0
    for i in range(36,len(candles)):
        c=candles[i]
        prior=candles[:i]
        sig=signal(prior)
        day=datetime.fromtimestamp(c['time'],timezone.utc).strftime('%Y-%m-%d')
        dayloss=daily_realized.get(day,0)
        if pos:
            # Intrabar conservative rule: stop before target, gap through stop gets open price.
            if c['low']<=pos['stop']:
                raw=min(c['open'],pos['stop']);reason='STOP'
            elif c['high']>=pos['target']:
                raw=pos['target'];reason='TARGET'
            else:raw=None;reason=None
            if raw is not None:
                out=raw*(1-SLIPPAGE)
                proceeds=pos['qty']*out
                exit_fee=proceeds*FEE
                realized=proceeds-exit_fee-(pos['qty']*pos['entry']+pos['entry_fee'])
                cash+=proceeds-exit_fee
                trades.append({'entry_time':pos['time'],'exit_time':c['time'],'entry':round(pos['entry'],6),'exit':round(out,6),'qty':pos['qty'],'pnl':round(realized,6),'exit_reason':reason})
                daily_realized[day]=daily_realized.get(day,0)+realized
                pos=None
        if sig.get('buy') and pos is None:
            signals+=1
            if c['time']-candles[i-1]['time']!=300:
                # A missing candle makes the next-open fill untrustworthy.
                blocked+=1
            elif daily_realized.get(day,0)<=-initial*DAILY_MAX:
                blocked+=1
            else:
                price=c['open']*(1+SLIPPAGE)
                distance=max(sig['atr']*1.5,price*.003)
                qty=min(initial*RISK_PER_TRADE/distance,cash*POSITION_FRACTION/(price*(1+FEE)))
                if qty>0 and qty*price>=5:
                    fee=qty*price*FEE;cash-=qty*price+fee
                    pos={'qty':qty,'entry':price,'entry_fee':fee,'stop':price-distance,'target':price+2*distance,'time':c['time']}
                    # No exit on entry bar: conservative about fill/stop ordering in 5m OHLC.
                else:blocked+=1
        equity=cash+(pos['qty']*c['close'] if pos else 0)
        curves.append({'time':c['time'],'equity':round(equity,5)})
    final=curves[-1]['equity']
    peak=initial;max_dd=0.0
    for point in curves:
        peak=max(peak,point['equity']);max_dd=max(max_dd,(peak-point['equity'])/peak*100 if peak else 0)
    wins=sum(x['pnl']>0 for x in trades)
    total_trade_pnl=sum(x['pnl'] for x in trades)
    avg_pnl=total_trade_pnl/len(trades) if trades else None
    gaps=sum(1 for a,b in zip(candles,candles[1:]) if b['time']-a['time']>300)
    gross_gain=sum(max(0,x['pnl']) for x in trades)
    gross_loss=-sum(min(0,x['pnl']) for x in trades)
    return {'ok':True,'candles':len(candles),'start':candles[36]['time'],'end':candles[-1]['time'],
            'starting_cash':initial,'final_equity':round(final,4),'net_pnl':round(final-initial,4),
            'return_pct':round((final/initial-1)*100,3),'buy_hold_pct':round((candles[-1]['close']/candles[36]['open']-1)*100,3),
            'max_drawdown_pct':round(max_dd,3),'signals':signals,'blocked':blocked,
            'closed_trades':len(trades),'wins':wins,
            'avg_closed_trade_pnl':round(avg_pnl,5) if avg_pnl is not None else None,
            'gaps_over_5m':gaps,'data_quality_warning':('Feed storico discontinuo: risultati da interpretare con cautela' if gaps else None),'win_rate_pct':round(wins/len(trades)*100,2) if trades else None,
            'profit_factor':round(gross_gain/gross_loss,3) if gross_loss else None,
            'open_position':bool(pos),'trades':trades[-40:],'curve':curves[::max(1,len(curves)//80)],
            'assumptions':'Segnale sulla candela chiusa precedente, entrata all’open successivo, long spot senza leva; stop/target intrabar con stop prioritario; commissioni 0,25% e slippage 0,05% per lato. Ingressi saltati dopo intervalli storici mancanti. Nessuna uscita nella barra di ingresso. Non riproduce order book, latenza, imposte o liquidazioni.'}


def validate_holdout(candles, starting_cash=105.0):
    """Chronological 70/30 out-of-sample diagnostic with 36-bar indicator warmup.

    This does not optimize parameters, claim independence, or persist trades.
    Training and holdout are each separate paper simulations; capital resets.
    """
    if len(candles)<180:
        return {'ok':False,'error':'Validazione non disponibile: servono almeno 180 candele chiuse',
                'candles':len(candles)}
    check=test_strategy(candles,starting_cash=starting_cash)
    if not check['ok']:
        return check
    boundary=int(len(candles)*0.70)
    train=test_strategy(candles[:boundary],starting_cash=starting_cash)
    holdout=test_strategy(candles[boundary-36:],starting_cash=starting_cash)
    if not train['ok'] or not holdout['ok']:
        return {'ok':False,'error':'Impossibile validare i due segmenti'}
    trades=holdout['closed_trades']
    enough=trades>=30 and holdout['gaps_over_5m']==0 and train['gaps_over_5m']==0
    return {
        'ok':True,'candles':len(candles),'split_index':boundary,
        'train':train,'holdout':holdout,
        'train_candles':boundary,
        'holdout_candles':len(candles)-boundary,
        'holdout_start_time':candles[boundary]['time'],
        'enough_evidence':enough,
        'assessment':('Campione preliminare, NON sufficiente per sostenere redditività'
                      if not enough else
                      'Campione con almeno 30 trade: serve comunque verifica su periodi molto più lunghi e mercati diversi'),
        'method':'Separazione cronologica 70/30, 36 candele passate usate solo per riscaldare gli indicatori della verifica finale; capitale virtuale reimpostato nei due segmenti, nessuna selezione dei parametri.'
    }
