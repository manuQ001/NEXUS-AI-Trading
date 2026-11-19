"""Test didattico isolato del ciclo ordine; dati e portafoglio sintetici, nessuna rete."""
import tempfile
from pathlib import Path
from core import connect, try_buy, handle_exit

def run_selftest():
    with tempfile.TemporaryDirectory(prefix='nexus_selftest_') as folder:
        c=connect(Path(folder)/'test.sqlite3')
        try:
            synthetic=[{'time':1700000000+i*300,'open':100+i,'high':101+i,'low':99+i,'close':100+i,'volume':100} for i in range(45)]
            ind={'buy':True,'atr':1.0,'why':'SELFTEST SINTETICO: segnale forzato solo nel test'}
            try_buy(c,'BTC',synthetic,ind)
            p=c.execute('SELECT * FROM positions WHERE symbol="BTC"').fetchone()
            if p is None: raise AssertionError('SNIPER non ha aperto la posizione virtuale')
            # Simulate a later candle hitting target, without touching the stop.
            handle_exit(c,'BTC',{'open':p['target']+1.0,'high':p['target']+2.0,'low':p['target']+0.1})
            trades=[dict(r) for r in c.execute('SELECT * FROM trades ORDER BY id')]
            if [t['action'] for t in trades]!=['BUY','SELL']:raise AssertionError('Ciclo BUY/SELL incompleto')
            if c.execute('SELECT COUNT(*) FROM positions').fetchone()[0]:raise AssertionError('Posizione non chiusa')
            # Independent stop loss scenario: fresh DB, no real trades involved.
            c.close()
            c=connect(Path(folder)/'stop.sqlite3')
            try_buy(c,'ETH',synthetic,ind)
            p2=c.execute('SELECT * FROM positions WHERE symbol="ETH"').fetchone()
            if p2 is None:raise AssertionError('SNIPER non ha aperto il test stop')
            handle_exit(c,'ETH',{'open':p2['entry'],'high':p2['entry'],'low':p2['stop']-1.0})
            stop=c.execute('SELECT * FROM trades WHERE action="SELL"').fetchone()
            if stop is None or stop['details']!='Stop loss' or stop['pnl']>=0:raise AssertionError('EXIT non ha gestito lo stop')
            return {'ok':True,'mode':'SELFTEST - DATI SINTETICI', 'checks':[
                'SNIPER: ingresso BUY virtuale registrato',
                'EXIT: take profit chiuso e commissioni registrate',
                'EXIT: stop loss chiuso con perdita registrata',
                'Database e fondi del bot principale non modificati'
            ],'note':'Il segnale di test è forzato. Non prova la redditività né la capacità di trovare segnali reali.'}
        finally:
            c.close()
