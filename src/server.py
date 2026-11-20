"""Local dashboard server, no third-party packages or external-order execution."""
import json, sys, threading, webbrowser, time, sqlite3
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
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
# Notifications contain committed local PAPER state, never synthetic transactions.
EVENT_CONDITION=threading.Condition()
EVENT_HISTORY=deque(maxlen=128)
EVENT_SERIAL=0

def publish_paper_event(kind,payload,timestamp=None):
    global EVENT_SERIAL
    if kind not in ('PAPER_TICK','PAPER_JOURNAL','PAPER_PROFILE','PAPER_MINT','PAPER_QUOTES'):raise ValueError('Unknown event')
    with EVENT_CONDITION:
        EVENT_SERIAL+=1
        item={'id':EVENT_SERIAL,'kind':kind,
              'time':int(time.time()) if timestamp is None else int(timestamp),
              'data':payload}
        EVENT_HISTORY.append(item)
        EVENT_CONDITION.notify_all()
    return item

def events_after(last_id):
    with EVENT_CONDITION:
        return [dict(item) for item in EVENT_HISTORY if item['id']>last_id]

# Recent manual DEX Scout quote fallback for local USD-credit DEMO ONLY.
# Bounded to 16 mints and 5 minutes. Never used by the BTC/ETH strategy.
MEME_SCOUT_QUOTES={}
MEME_SCOUT_TTL_SECONDS=300
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
        elif path=='/api/meme-events':
            # Local EventSource notifications; client fetches actual state separately.
            try:cursor=max(0,int(self.headers.get('Last-Event-ID','0')))
            except (TypeError,ValueError):cursor=0
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Accel-Buffering','no')
            self.end_headers()
            try:
                self.wfile.write(b'retry: 2000\n\n')
                self.wfile.flush()
                while True:
                    with EVENT_CONDITION:
                        pending=[dict(item) for item in EVENT_HISTORY if item['id']>cursor]
                        if not pending:
                            EVENT_CONDITION.wait(timeout=15)
                            pending=[dict(item) for item in EVENT_HISTORY if item['id']>cursor]
                    if not pending:self.wfile.write(b': connected\n\n')
                    else:
                        for item in pending:
                            cursor=item['id']
                            msg=('id: '+str(cursor)+'\nevent: paper\ndata: '+
                                 json.dumps(item,ensure_ascii=False)+'\n\n')
                            self.wfile.write(msg.encode('utf-8'))
                    self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError):
                return
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
        elif path=='/api/meme-risk-intelligence':
            from meme_risk_intelligence import report as risk_report
            with LOCK:
                c=connect()
                try:
                    result=risk_report(c)
                    c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/v4-ai-shadow':
            from v4_ai_shadow import report as ai_report
            with LOCK:
                c=connect()
                try:
                    data=ai_report(c)
                    c.commit()
                finally:c.close()
            self.out(data)
        elif path=='/api/v4-agents':
            from v4_agents import report as v4_report
            with LOCK:
                c=connect()
                try:
                    data=v4_report(c)
                    c.commit()
                finally:c.close()
            self.out(data)
        elif path=='/api/meme-decision-timeline':
            from meme_timeline import timeline
            with LOCK:
                c=connect()
                try:result=timeline(c)
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-shadow':
            from meme_shadow import report as shadow_report
            with LOCK:
                c=connect()
                try:
                    result=shadow_report(c)
                    c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-market-candles':
            from meme_prices import observed_candles
            query=parse_qs(urlsplit(self.path).query)
            address=query.get('address',[''])[0]
            try:
                interval=int(query.get('interval',['60'])[0])
                with LOCK:
                    c=connect()
                    try:
                        result=observed_candles(c,address,interval_seconds=interval)
                    finally:c.close()
                self.out(result)
            except (ValueError,TypeError):
                self.out({'error':'Mint o intervallo non valido'},status=400)
        elif path=='/api/meme-market-pulse':
            from meme_prices import snapshot as market_snapshot
            with LOCK:
                c=connect()
                try:
                    result=market_snapshot(c)
                    c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-mints':
            from meme_mints import FEED
            self.out(FEED.state())
        elif path=='/api/meme-live':
            from meme_live import INBOX
            self.out(INBOX.state())
        elif path=='/api/meme-desk':
            from meme_desk import report as desk_report
            from meme_live import INBOX
            with LOCK:
                c=connect()
                try:
                    result=desk_report(c,stream=INBOX.state())
                    c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-intelligence':
            from meme_intelligence import report as strategy_report
            with LOCK:
                c=connect()
                try:
                    result=strategy_report(c)
                    c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-auto':
            from meme_auto import status
            with LOCK:
                c=connect()
                try:
                    result=status(c);c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-demo':
            from meme_portfolio import portfolio
            with LOCK:
                c=connect()
                try: result=portfolio(c);c.commit()
                finally:c.close()
            self.out(result)
        elif path=='/api/meme-scout':
            # Manual, bounded public-data research. No SQLite writes, no orders.
            try:
                from meme_scout import scan
                result=scan()
                # Store only server-retrieved quotes, never prices from the browser.
                from meme_scout import ADDRESS
                with LOCK:
                    MEME_SCOUT_QUOTES.clear()
                    observed=time.time()
                    for token in result.get('candidates',[])[:12]:
                        mint=token.get('address')
                        price=token.get('price_usd')
                        if isinstance(mint,str) and ADDRESS.fullmatch(mint) and isinstance(price,(int,float)) and price>0:
                            MEME_SCOUT_QUOTES[mint]={
                                'quote':{'price_usd':price,'liquidity_usd':token.get('liquidity_usd'),
                                         'volume_24h_usd':token.get('volume_24h_usd'),
                                         'symbol':token.get('symbol')},
                                'observed_at':observed
                            }
                self.out(result)
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
        if path=='/api/v4-toggle':
            origin=self.headers.get('Origin')
            fetch_site=self.headers.get('Sec-Fetch-Site')
            if (self.headers.get('X-NEXUS-Demo-Click')!='1'
                    or self.headers.get('Content-Length','0')!='0'
                    or (origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'))
                    or (fetch_site and fetch_site not in ('same-origin','none'))):
                self.out({'ok':False,'error':'Richiesta V4 non autorizzata'},403);return
            from v4_agents import initialize as init_v4,report as v4_report
            with LOCK:
                c=connect()
                try:
                    init_v4(c)
                    c.execute('UPDATE v4_paper_state SET enabled=1-enabled WHERE id=1')
                    c.commit()
                    current=v4_report(c)
                finally:c.close()
            self.out({'ok':True,'v4':current});return
        if path=='/api/meme-auto-toggle':
            origin=self.headers.get('Origin')
            fetch_site=self.headers.get('Sec-Fetch-Site')
            if (self.headers.get('X-NEXUS-Demo-Click')!='1'
                    or self.headers.get('Content-Length','0')!='0'
                    or (origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'))
                    or (fetch_site and fetch_site not in ('same-origin','none'))):
                self.out({'ok':False,'error':'Richiesta demo non autorizzata'},403);return
            from meme_auto import init_auto,status
            with LOCK:
                c=connect()
                try:
                    init_auto(c)
                    current=c.execute('SELECT enabled FROM meme_auto_state WHERE id=1').fetchone()[0]
                    c.execute('UPDATE meme_auto_state SET enabled=?,last_status=? WHERE id=1',
                              (0 if current else 1,'SOSPESO' if current else 'ATTIVO'))
                    c.commit()
                    report=status(c)
                finally:c.close()
            self.out({'ok':True,'auto':report});return
        if path=='/api/meme-demo-trade':
            # Click-only, zero-body, same-origin action. No real exchange integrations.
            from urllib.parse import parse_qs
            from meme_scout import ADDRESS
            from meme_portfolio import indicative_quote, trade, portfolio, get_fx
            origin=self.headers.get('Origin')
            fetch_site=self.headers.get('Sec-Fetch-Site')
            authorized=(self.headers.get('X-NEXUS-Demo-Click')=='1'
                        and self.headers.get('Content-Length','0')=='0'
                        and (not origin or origin in ('http://127.0.0.1:8765','http://localhost:8765'))
                        and (not fetch_site or fetch_site in ('same-origin','none')))
            if not authorized:
                self.out({'ok':False,'error':'Richiesta demo non autorizzata'},403);return
            query=parse_qs(urlsplit(self.path).query)
            address=query.get('address',[''])[0];action=query.get('action',[''])[0]
            if not ADDRESS.fullmatch(address) or action not in ('BUY','SELL'):
                self.out({'ok':False,'error':'Mint o azione non validi'},400);return
            try:
                # First try a current public quote; if unavailable, use a recent
                # server-side Scout observation for DEMO only. No browser prices.
                source='DEX Screener richiesta corrente'
                try:
                    quote=indicative_quote(address)
                except (OSError,ValueError,TypeError,KeyError,TimeoutError) as quote_error:
                    with LOCK:
                        cached=MEME_SCOUT_QUOTES.get(address)
                    if not cached or time.time()-cached['observed_at']>MEME_SCOUT_TTL_SECONDS:
                        raise ValueError('Prezzo non disponibile: aggiorna Analizza Solana e riprova. ('+
                                         type(quote_error).__name__+')')
                    quote=dict(cached['quote'])
                    source='MEME SCOUT: prezzo osservato negli ultimi 5 minuti (non live)'
                with LOCK:
                    c=connect()
                    try:
                        fx=get_fx(c)
                        outcome=trade(c,address,action,quote,fx)
                        state=portfolio(c);c.commit()
                    finally:c.close()
                outcome['quote_source']=source
                if source.startswith('MEME SCOUT'):
                    outcome.setdefault('warnings',[]).append('Prezzo recente da Scout, non aggiornato al momento del click')
                self.out({'ok':True,'trade':outcome,'account':state})
            except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError,TimeoutError,sqlite3.Error) as exc:
                self.out({'ok':False,'error':'Quick demo non eseguibile: '+str(exc)[:160]},400)
            return
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


def meme_auto_loop(stop, interval_seconds=10):
    """Experimental MEME PAPER engine, independent of dashboard and BTC/ETH."""
    from meme_auto import tick
    from meme_prices import changes_after,refresh_watchlist
    from meme_live import INBOX
    from meme_scout import scan_profiles
    with LOCK:
        db=connect()
        try:previous_event_id=db.execute(
            'SELECT COALESCE(MAX(id),0) FROM meme_auto_journal'
        ).fetchone()[0] if db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meme_auto_journal'"
        ).fetchone() else 0
        finally:db.close()
    with LOCK:
        db=connect()
        try:
            from meme_prices import initialize as init_market
            init_market(db)
            previous_quote_id=db.execute(
                'SELECT COALESCE(MAX(id),0) FROM meme_quote_changes').fetchone()[0]
        finally:db.close()
    while not stop.is_set():
        try:
            with LOCK:
                c=connect()
                try:
                    live_profiles=INBOX.pop()
                    if live_profiles:
                        # Enrich one bounded batch via the documented REST quote API.
                        # Failure does not bypass deterministic filters.
                        state=tick(c,scout=lambda:scan_profiles(live_profiles),
                                   force_scan=True)
                    else:
                        state=tick(c)
                    # Separate quote monitor runs even when no PAPER position is
                    # open. It never changes cash, orders or risk state.
                    monitor_result=refresh_watchlist(c)
                    from meme_shadow import evaluate as evaluate_shadow
                    shadow_result=evaluate_shadow(c)
                    from meme_risk_intelligence import inspect_next as inspect_next_risk
                    risk_result=inspect_next_risk(c)
                    # Isolate experimental V4 errors from the established
                    # MEME scanner, Shadow and legacy PAPER worker.
                    c.execute('SAVEPOINT v4_experiment')
                    try:
                        from v4_agents import tick as v4_tick
                        v4_result=v4_tick(c)
                        c.execute('RELEASE SAVEPOINT v4_experiment')
                    except Exception as v4_exc:
                        c.execute('ROLLBACK TO SAVEPOINT v4_experiment')
                        c.execute('RELEASE SAVEPOINT v4_experiment')
                        print('NEXUS V4 PAPER experiment: '+type(v4_exc).__name__,flush=True)
                    c.commit()
                    new_events=[dict(row) for row in c.execute(
                        'SELECT id FROM meme_auto_journal WHERE id>? ORDER BY id LIMIT 60',
                        (previous_event_id,))]
                    if new_events:previous_event_id=max(x['id'] for x in new_events)
                    changed_quotes=changes_after(c,previous_quote_id,limit=40)
                    if changed_quotes:
                        previous_quote_id=max(x['id'] for x in changed_quotes)
                finally:c.close()
            if changed_quotes:
                publish_paper_event('PAPER_QUOTES',{
                    'count':len(changed_quotes),
                    'last_change_id':previous_quote_id,
                    'source':'DEX_SCREENER_REST_SERVER_OBSERVATIONS',
                    'sample_server_time':changed_quotes[-1]['observed_at']})
            publish_paper_event('PAPER_TICK',{'last_tick':state['last_tick'],
                'status':state['status'],'last_scan':state['last_scan']})
            if live_profiles:
                publish_paper_event('PAPER_PROFILE',{'received':len(live_profiles),
                    'source':'DEX Screener token profile WebSocket'})
            if new_events:
                publish_paper_event('PAPER_JOURNAL',{'last_journal_id':previous_event_id,
                    'count':len(new_events)})
        except Exception as exc:
            print('NEXUS MEME PAPER monitor: '+type(exc).__name__,flush=True)
        if stop.wait(interval_seconds):break


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
    from meme_live import listen
    from meme_mints import listen as listen_mints
    threading.Thread(target=listen,args=(stop,),daemon=True,
                     name='NEXUS-MEME-Profile-Stream').start()
    threading.Thread(target=listen_mints,args=(stop,),
                     kwargs={'publish':publish_paper_event},daemon=True,
                     name='NEXUS-Solana-Mint-Stream').start()
    threading.Thread(target=meme_auto_loop,args=(stop,),daemon=True).start()
    from v4_ai_shadow import background_cycle
    threading.Thread(target=background_cycle,args=(connect,LOCK,stop),
                     daemon=True,name='NEXUS-V4-Real-AI-Shadow').start()
    print(f'NEXUS AI {VERSION} — SOLO SIMULAZIONE')
    print('Dashboard: http://127.0.0.1:8765')
    print('Monitoraggio BTC/ETH ogni 30 s mentre il programma resta acceso, anche senza browser.')
    print('MEME AUTO PAPER: monitor ~10 s, scansione REST ogni 60 s, discovery profili via WebSocket quando disponibile; nessun ordine reale.')
    print('Premi CTRL+C per chiudere. Nessuna operazione reale.')
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close()

if __name__=='__main__':main()
