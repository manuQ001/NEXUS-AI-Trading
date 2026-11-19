"""Local dashboard server, no third-party packages or external-order execution."""
import json, sys, threading, webbrowser, time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from core import connect, startup_events, snapshot, refresh, load_closed_history, historical_coverage
from selftest import run_selftest
from backtest import test_strategy, validate_holdout
from core import fetch_kraken
from maintenance import run_tests, check_updates, VERSION, ROOT
from downloader import download_if_available, read_staged

LOCK=threading.Lock()
PAGE=(Path(__file__).parent/'dashboard.html').read_bytes()
MAINTENANCE_REPORT=ROOT/'maintenance_status.json'


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
            self.out(data)
        elif path=='/api/selftest':
            try: self.out(run_selftest())
            except Exception as exc: self.out({'ok':False,'error':str(exc),'mode':'SELFTEST - DATI SINTETICI'},500)
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
                    candles=load_closed_history(c,symbol)
                    c.close()
                if len(candles)<70:
                    candles=fetch_kraken(symbol)
                    source='Kraken OHLC 5m recente (solo candele chiuse)'
                else:
                    source='Archivio SQLite locale Kraken OHLC 5m (solo candele chiuse)'
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
            data['refresh_result']=status;self.out(data)
        else:self.out({'error':'Endpoint non esistente'},404)
    def log_message(self,format,*args):
        if '/api/' not in str(args):super().log_message(format,*args)

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
    print(f'NEXUS AI {VERSION} — SOLO SIMULAZIONE')
    print('Dashboard: http://127.0.0.1:8765')
    print('Premi CTRL+C per chiudere. Nessuna operazione reale.')
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close()

if __name__=='__main__':main()
