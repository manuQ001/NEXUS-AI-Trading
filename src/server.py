"""Local dashboard server, no third-party packages or external-order execution."""
import json, sys, threading, webbrowser, time, sqlite3
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from core import connect, startup_events, snapshot, refresh, load_closed_history, historical_coverage
from selftest import run_selftest
from backtest import test_strategy, validate_holdout
from core import fetch_kraken, daily_loss
from agents import review, local_ai_advice, attach_market_quality
from external_ai import external_ai_advice
from research_journal import record as record_ai_research, latest as latest_ai_research
from execution import execution_stress_scenarios
from orderbook import fetch_depth, depth_study, inspect_book_quality
from maintenance import run_tests, check_updates, VERSION, ROOT
from downloader import download_if_available, read_staged

LOCK=threading.Lock()
PAGE=(Path(__file__).parent/'dashboard.html').read_bytes()
MAINTENANCE_REPORT=ROOT/'maintenance_status.json'
# Local process state only: no credentials and no scheduled real orders.
MONITOR={'started_at':None,'last_attempt':None,'last_success':None,
         'status':{},'error':None,'interval_seconds':30}


class Handler(BaseHTTPRequestHandler):
    def out(self,obj,status=200):
        payload=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/':
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(PAGE)));self.end_headers();self.wfile.write(PAGE)
        elif path=='/api/state':
            with LOCK:
                c=connect();startup_events(c);data=snapshot(c);c.close()
                data['monitor']=dict(MONITOR)
            self.out(data)
        elif path=='/api/selftest':
            try: self.out(run_selftest())
            except Exception as exc: self.out({'ok':False,'error':str(exc),'mode':'SELFTEST - DATI SINTETICI'},500)
        elif path=='/api/agents':
            from urllib.parse import parse_qs
            params=parse_qs(urlsplit(self.path).query)
            symbol=params.get('symbol',['BTC'])[0]
            if symbol not in ('BTC','ETH'):
                self.out({'ok':False,'error':'Simbolo non valido'},400);return
            try:
                with LOCK:
                    c=connect()
                    snap=snapshot(c)
                    realized=daily_loss(c)
                    c.close()
                candles=snap.get('candles',{}).get(symbol,[])
                if not candles:
                    self.out({'ok':False,'error':'Esegui Aggiorna mercato prima di consultare gli agenti'},400);return
                report=review(symbol,candles,snap.get('indicators',{}).get(symbol,{}) or {},
                              positions=snap['positions'],daily_realized=realized,
                              feed_ok=snap.get('status',{}).get(symbol)=='OK',
                              core_cash=next((w['cash'] for w in snap['wallets'] if w['strategy']=='core'),None))
                # Two read-only REST snapshots on explicit "Consulta agenti" click.
                # Failure is visible as UNAVAILABLE, never silently a book PASS.
                try:
                    first=fetch_depth(symbol,count=20)
                    latest=fetch_depth(symbol,count=20)
                    quality=inspect_book_quality(first,latest)
                    report=attach_market_quality(report,quality,book=latest)
                except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError) as book_exc:
                    report=attach_market_quality(report,error=type(book_exc).__name__)
                self.out({'ok':True,'report':report})
            except (ValueError,TypeError) as exc:
                self.out({'ok':False,'error':str(exc)[:200]},400)
        elif path=='/api/ai-review':
            self.out({'ok':False,'error':'Usa il pulsante Analisi AI (POST protetto)'},405)
        elif path=='/api/meme-risk':
            from urllib.parse import parse_qs
            address=parse_qs(urlsplit(self.path).query).get('address',[''])[0]
            try:
                from rug_guard import inspect
                self.out(inspect(address))
            except ValueError as exc:
                # Address errors are client errors; provider failures remain unverified.
                if address=='' or len(address)>44 or any(ch in address for ch in '/%.?&'):
                    self.out({'ok':False,'error':'Mint Solana non valido','meme_execution':'BLOCKED'},400)
                else:
                    self.out({'ok':False,'error':'Controllo on-chain non disponibile: '+type(exc).__name__,
                              'meme_execution':'BLOCKED','status':'NON_VERIFICATO'},503)
            except (OSError,TypeError,KeyError,IndexError,OverflowError,TimeoutError) as exc:
                self.out({'ok':False,'error':'GoPlus non disponibile: '+type(exc).__name__,
                          'meme_execution':'BLOCKED','status':'NON_VERIFICATO'},503)
        elif path=='/api/meme-whales':
            from urllib.parse import parse_qs
            address=parse_qs(urlsplit(self.path).query).get('address',[''])[0]
            from whale_tracker import ADDRESS
            if not ADDRESS.fullmatch(address):
                self.out({'ok':False,'error':'Mint Solana non valido',
                          'meme_execution':'BLOCKED'},400);return
            try:
                from whale_tracker import inspect
                self.out(inspect(address))
            except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError,TimeoutError) as exc:
                self.out({'ok':False,'status':'NON_VERIFICATO','meme_execution':'BLOCKED',
                          'error':'RPC Solana non disponibile o non valido: '+type(exc).__name__},503)
        elif path=='/api/meme-scout':
            # Manual, bounded public-data research. No SQLite writes, no orders.
            try:
                from meme_scout import scan
                self.out(scan())
            except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError,TimeoutError) as exc:
                self.out({'ok':False,'mode':'READ_ONLY','meme_execution':'BLOCKED',
                          'error':'Fonte memecoin non disponibile o non valida: '+type(exc).__name__},503)
        elif path=='/api/orderbook-study':
            from urllib.parse import parse_qs
            symbol=parse_qs(urlsplit(self.path).query).get('symbol',['BTC'])[0]
            if symbol not in ('BTC','ETH'):
                self.out({'ok':False,'error':'Simbolo non valido'},400);return
            try:
                # Two read-only HTTP snapshots; never used to approve paper orders.
                first=fetch_depth(symbol,count=20)
                book=fetch_depth(symbol,count=20)
                report=depth_study(book,order_eur=25)
                report['quality']=inspect_book_quality(first,book)
                self.out({'ok':True,'report':report})
            except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
                self.out({'ok':False,'error':'Book Kraken non disponibile o non valido: '+type(exc).__name__},503)
        elif path=='/api/execution-study':
            from urllib.parse import parse_qs
            symbol=parse_qs(urlsplit(self.path).query).get('symbol',['BTC'])[0]
            if symbol not in ('BTC','ETH'):
                self.out({'ok':False,'error':'Simbolo non valido'},400);return
            with LOCK:
                c=connect()
                prices=snapshot(c)['prices']
                c.close()
            mid=prices.get(symbol)
            if not mid:
                self.out({'ok':False,'error':'Aggiorna il mercato per ottenere un prezzo di riferimento'},400);return
            try:
                report=execution_stress_scenarios(mid)
                report['symbol']=symbol
                self.out({'ok':True,'report':report})
            except (ValueError,TypeError,OverflowError):
                self.out({'ok':False,'error':'Prezzo di riferimento non valido'},400)
        elif path=='/api/history':
            with LOCK:
                c=connect()
                report={sym:historical_coverage(c,sym) for sym in ('BTC','ETH')}
                c.close()
            self.out({'ok':True,'markets':report})
        elif path in ('/api/backtest','/api/validation'):
            from urllib.parse import parse_qs
            params=parse_qs(urlsplit(self.path).query)
            symbol=params.get('symbol',['BTC'])[0]
            if symbol not in ('BTC','ETH'):
                self.out({'ok':False,'error':'Simbolo non valido'},400);return
            try:
                # Read-only study: never uses the trading database.
                with LOCK:
                    c=connect()
                    candles=load_closed_history(c,symbol,limit=1500)
                    c.close()
                if len(candles)<70:
                    candles=fetch_kraken(symbol)
                    source='Kraken OHLC 5m recente (solo candele chiuse)'
                else:
                    source='Archivio SQLite locale Kraken OHLC 5m (ultime 1500 candele chiuse per evitare blocchi CPU)'
                report=validate_holdout(candles) if path=='/api/validation' else test_strategy(candles)
                report['symbol']=symbol
                report['data_source']=source
                self.out(report)
            except Exception as exc:
                self.out({'ok':False,'error':'Backtest non disponibile: '+str(exc)[:200]},503)
        elif path=='/api/tests':
            report=run_tests();self.out(report)
        elif path=='/api/maintenance':
            try:self.out(json.loads(MAINTENANCE_REPORT.read_text('utf-8')))
            except (OSError,ValueError):self.out({'last_run':None,'note':'Test automatici non ancora eseguiti'})
        elif path=='/api/updates':
            result=check_updates()
            staged=read_staged()
            if staged:result['staged_version']=staged['version'];result['note']='Aggiornamento scaricato e verificato. Chiudi NEXUS e applica con: py updater.py --apply-staged'
            self.out(result)
        elif path=='/api/refresh':
            with LOCK:
                c=connect();startup_events(c);status=refresh(c);data=snapshot(c);c.close()
                data['monitor']=dict(MONITOR)
            data['refresh_result']=status;self.out(data)
        else:self.out({'error':'Endpoint non esistente'},404)
    def do_POST(self):
        path=urlsplit(self.path).path
        if path!='/api/ai-review':
            self.out({'ok':False,'error':'Endpoint non esistente'},404);return
        origin=self.headers.get('Origin')
        fetch_site=self.headers.get('Sec-Fetch-Site')
        if (self.headers.get('X-NEXUS-Research-Click')!='1'
                or (origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'))
                or (fetch_site and fetch_site not in ('same-origin','none'))
                or self.headers.get('Content-Length','0')!='0'):
            self.out({'ok':False,'error':'Richiesta AI non autorizzata'},403);return
        from urllib.parse import parse_qs
        params=parse_qs(urlsplit(self.path).query)
        symbol=params.get('symbol',['BTC'])[0]
        if symbol not in ('BTC','ETH'):
            self.out({'ok':False,'error':'Simbolo non valido'},400);return
        try:
            with LOCK:
                c=connect()
                try:
                    snap=snapshot(c); realized=daily_loss(c)
                finally:
                    c.close()
            candles=snap.get('candles',{}).get(symbol,[])
            if not candles:
                self.out({'ok':False,'error':'Aggiorna il mercato prima di interrogare il modello'},400);return
            base=review(symbol,candles,snap.get('indicators',{}).get(symbol,{}) or {},
                        positions=snap['positions'],daily_realized=realized,
                        feed_ok=snap.get('status',{}).get(symbol)=='OK',
                        core_cash=next((w['cash'] for w in snap['wallets']
                                       if w['strategy']=='core'),None))
            base['reference_close']=float(candles[-1]['close'])
            import os
            advice=(external_ai_advice(base)
                    if os.environ.get('NEXUS_OPENAI_MODEL') or os.environ.get('NEXUS_OPENAI_API_KEY')
                    else local_ai_advice(base))
            if advice.get('available'):
                # A journal disk failure cannot discard an already-paid
                # advisory response or cause users to repeat a billable call.
                try:
                    with LOCK:
                        c=connect()
                        try:
                            journal_result=record_ai_research(c,base,advice)
                            c.commit()
                        finally:
                            c.close()
                    advice['research_journal']=journal_result
                except (OSError,ValueError,TypeError) as exc:
                    advice['research_journal']={'saved':False,
                        'reason':'JOURNAL_UNAVAILABLE','error_type':type(exc).__name__}
                except sqlite3.Error:
                    advice['research_journal']={'saved':False,
                        'reason':'JOURNAL_UNAVAILABLE','error_type':'DatabaseError'}
            self.out({'ok':True,'advice':advice})
        except (ValueError,TypeError) as exc:
            self.out({'ok':False,'error':str(exc)[:200]},400)
    def log_message(self,format,*args):
        if '/api/' not in str(args):super().log_message(format,*args)

def market_monitor_loop(stop, interval_seconds=30):
    """Keep processing Kraken's closed 5-minute candles without a web browser.

    The existing process_candles() deduplicates by candle timestamp and does
    not backfill paper trades. Both this worker and browser refresh share LOCK.
    Every 30 s provides multiple chances to observe a candle within the
    existing 90 s entry-freshness window. No real exchange orders exist.
    """
    if not 10<=interval_seconds<=300:
        raise ValueError('Intervallo monitor non valido')
    with LOCK:
        MONITOR.update(started_at=int(time.time()),interval_seconds=interval_seconds,
                       error=None)
    while not stop.is_set():
        try:
            with LOCK:
                MONITOR['last_attempt']=int(time.time())
                c=connect()
                try:
                    status=refresh(c)
                finally:
                    c.close()
                MONITOR['status']=dict(status)
                if any(value=='OK' for value in status.values()):
                    MONITOR['last_success']=int(time.time())
                MONITOR['error']=None if all(value=='OK' for value in status.values()) else (
                    'Uno o più feed Kraken non disponibili')
        except Exception as exc:
            # A transient network/SQLite error must not terminate monitoring.
            with LOCK:
                MONITOR['error']='Monitor: '+type(exc).__name__
            print('NEXUS monitor: '+type(exc).__name__,flush=True)
        if stop.wait(interval_seconds):
            break


def maintenance_loop(stop):
    # Automated offline validation (no trades, no user database mutations).
    while not stop.is_set():
        results=run_tests()
        report={'last_run':int(time.time()),'version':VERSION,'tests_ok':results['ok'],'summary':results.get('output','')[-900:]}
        report['updates']=check_updates()
        if report['updates'].get('update_available'):
            report['download']=download_if_available(report['updates'])
        try:
            temp=MAINTENANCE_REPORT.with_suffix('.tmp')
            temp.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
            temp.replace(MAINTENANCE_REPORT)
        except OSError:pass
        # Daily check if the user has configured a trusted manifest; no code is installed.
        if stop.wait(6*3600):break

def main():
    c=connect();startup_events(c);c.close()
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    stop=threading.Event()
    threading.Thread(target=maintenance_loop,args=(stop,),daemon=True).start()
    threading.Thread(target=market_monitor_loop,args=(stop,),daemon=True).start()
    print(f'NEXUS AI {VERSION} — SOLO SIMULAZIONE')
    print('Dashboard: http://127.0.0.1:8765')
    print('Monitoraggio BTC/ETH ogni 30 s mentre il programma resta acceso, anche senza browser.')
    print('Premi CTRL+C per chiudere. Nessuna operazione reale.')
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close()

if __name__=='__main__':main()
