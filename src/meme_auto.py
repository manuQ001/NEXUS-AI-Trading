"""Autonomous Solana MEME trading simulation on the original €45 NEXUS wallet.

Only market-data requests and local SQLite bookkeeping. NEVER real orders,
signatures, wallet keys, swaps, or trade API calls. Experimental signals.
"""
import math
import time
import json
from meme_agents import review as review_meme_agents
from meme_portfolio import (initialize,trade,mark,portfolio,get_fx,indicative_quote,
                            MAX_POSITIONS, STAKE_EUR, SELL_COST)
from meme_scout import scan,ADDRESS

STOP_LOSS=-0.05  # Gross price/FX movement: excludes 3%+3% simulated fees
EMERGENCY_NET_STOP=-0.15 # Defensive net threshold; not an execution guarantee
TAKE_PROFIT=0.12
TRAIL_ARM=0.08
TRAIL_GAP=0.04
MAX_HOLD_SECONDS=900
SCAN_SECONDS=60
COOLDOWN_SECONDS=3600
MIN_AUTO_LIQUIDITY=500.0
MIN_AUTO_VOLUME=500.0
MAX_ENTRIES_PER_SCAN=3
MIN_ENTRY_LIQUIDITY=10000.0
MIN_ENTRY_VOLUME=20000.0
MAX_EQUITY_DRAWDOWN=0.10
MIN_POOL_AGE_HOURS=0.5
MIN_STAKE_EUR=1.5
MAX_INITIAL_FRACTION=0.10
CASH_RESERVE_FRACTION=0.20

def dynamic_stake(c,candidate,quote):
    """Conservative, deterministic paper sizing; no LLM controls the wallet."""
    w=c.execute("SELECT cash,initial FROM wallets WHERE strategy='meme'").fetchone()
    if w is None:return None
    cash=float(w['cash']);initial=float(w['initial'])
    liquidity=min(_number(candidate.get('liquidity_usd')) or 0,
                  _number(quote.get('liquidity_usd')) or 0)
    volume=min(_number(candidate.get('volume_24h_usd')) or 0,
               _number(quote.get('volume_24h_usd')) or 0)
    strength=min(liquidity,volume)
    if strength<MIN_AUTO_LIQUIDITY or not math.isfinite(initial) or initial<=0:return None
    if strength>=10000:desired=4.5
    elif strength>=2500:desired=3.0
    else:desired=MIN_STAKE_EUR
    cap=round(initial*MAX_INITIAL_FRACTION,2)
    available=round(cash-initial*CASH_RESERVE_FRACTION,2)
    stake=round(min(desired,cap,available),2)
    return stake if stake>=MIN_STAKE_EUR else None

def _number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) and x>=0 else None
    except (TypeError,ValueError,OverflowError):return None

def init_auto(c):
    initialize(c)
    c.execute('''CREATE TABLE IF NOT EXISTS meme_auto_state(
        id INTEGER PRIMARY KEY CHECK(id=1),
        enabled INTEGER NOT NULL DEFAULT 1,
        last_scan INTEGER NOT NULL DEFAULT 0,
        last_tick INTEGER NOT NULL DEFAULT 0,
        last_status TEXT NOT NULL DEFAULT 'NON_AVVIATO',
        last_error TEXT NOT NULL DEFAULT '')''')
    c.execute("INSERT OR IGNORE INTO meme_auto_state(id,enabled) VALUES(1,1)")
    c.execute('''CREATE TABLE IF NOT EXISTS meme_auto_trail(
        address TEXT PRIMARY KEY,peak_net_roi REAL NOT NULL,updated_at INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meme_auto_journal(
        id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp INTEGER NOT NULL,
        address TEXT, action TEXT NOT NULL,note TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS meme_agent_latest(
        id INTEGER PRIMARY KEY CHECK(id=1),updated_at INTEGER NOT NULL,
        report_json TEXT NOT NULL)''')

def status(c):
    init_auto(c)
    s=c.execute('SELECT * FROM meme_auto_state WHERE id=1').fetchone()
    agent_row=c.execute('SELECT * FROM meme_agent_latest WHERE id=1').fetchone()
    agent_report=json.loads(agent_row['report_json']) if agent_row else {
        'status':'NOT_STARTED','mode':'NOT_STARTED','agents':[]}
    guard=circuit_breaker(c)
    return {'agents_report':agent_report,'risk_circuit':guard,
            'agents_updated_at':agent_row['updated_at'] if agent_row else None,
            'enabled':bool(s['enabled']),'last_scan':s['last_scan'],
            'last_tick':s['last_tick'],'status':s['last_status'],
            'error':s['last_error'],'price_stop_pct':STOP_LOSS*100,
            'emergency_net_stop_pct':EMERGENCY_NET_STOP*100,'take_profit_pct':12,
            'trailing_activation_pct':8,'trailing_gap_points':4,
            'max_hold_minutes':15,'monitor_seconds':10,'scan_seconds':SCAN_SECONDS,
            'max_positions':MAX_POSITIONS,'max_entries_per_scan':MAX_ENTRIES_PER_SCAN,
            'min_entry_liquidity_usd':MIN_ENTRY_LIQUIDITY,
            'min_entry_volume_24h_usd':MIN_ENTRY_VOLUME,
            'drawdown_halt_pct':MAX_EQUITY_DRAWDOWN*100,
            'sizing':'DYNAMIC_EUR','min_stake_eur':MIN_STAKE_EUR,'max_initial_fraction':MAX_INITIAL_FRACTION,'cash_reserve_fraction':CASH_RESERVE_FRACTION,
            'mode':'AUTONOMOUS_PAPER_ONLY',
            'journal':[dict(x) for x in c.execute(
                'SELECT * FROM meme_auto_journal ORDER BY id DESC LIMIT 35')]}

def _log(c,now,address,action,note):
    c.execute('INSERT INTO meme_auto_journal(timestamp,address,action,note) VALUES(?,?,?,?)',
              (now,address,action,note[:280]))

def net_roi(p,price,fx):
    """Estimated net EUR ROI including modeled exit cost, not executable price."""
    price=_number(price)
    qty=_number(p.get('quantity'))
    cost=_number(p.get('cost_eur'))
    rate=_number(fx)
    if not price or not qty or not cost or not rate:return None
    return qty*price*rate*(1-SELL_COST)/cost-1

def gross_roi(p,price,fx):
    """Observed price/FX change before simulated trading costs."""
    price=_number(price)
    fx=_number(fx)
    entry=_number(p.get('entry_price_usd'))
    entry_fx=_number(p.get('entry_fx_usd_eur'))
    if not price or not fx or not entry or not entry_fx:return None
    return price*fx/(entry*entry_fx)-1

def entry_rejection(candidate,quote):
    """Extra filters for autonomous new entries; no certainty of sellability."""
    liquidity=min(_number(candidate.get('liquidity_usd')) or 0,
                  _number(quote.get('liquidity_usd')) or 0)
    volume=min(_number(candidate.get('volume_24h_usd')) or 0,
               _number(quote.get('volume_24h_usd')) or 0)
    if liquidity<MIN_ENTRY_LIQUIDITY:return 'LIQUIDITA_BASSA'
    if volume<MIN_ENTRY_VOLUME:return 'VOLUME_BASSO'
    age=_number(candidate.get('pool_age_hours'))
    if age is not None and age<MIN_POOL_AGE_HOURS:return 'POOL_TROPPO_RECENTE'
    return None

def circuit_breaker(c,now=None):
    """Pause new entries on estimated 10% total drawdown; allow existing exits."""
    p=portfolio(c,now=now)
    initial=float(p['starting_eur'])
    equity=float(p['equity_eur'])
    if initial<=0 or not math.isfinite(equity):
        return {'blocked':True,'reason':'EQUITY_NON_VALIDA'}
    drawdown=max(0.0,(initial-equity)/initial)
    return {'blocked':drawdown>=MAX_EQUITY_DRAWDOWN,
            'reason':'LIMITE_DRAWDOWN' if drawdown>=MAX_EQUITY_DRAWDOWN else 'OK',
            'drawdown_pct':round(drawdown*100,3),'equity_eur':round(equity,4),
            'threshold_pct':MAX_EQUITY_DRAWDOWN*100}

def decide_exit(p,price,now,fx=None,peak_roi=None):
    rate=fx if fx is not None else p.get('last_fx_usd_eur')
    roi=net_roi(p,price,rate)
    gross=gross_roi(p,price,rate)
    if roi is None or gross is None:return None
    if roi<=EMERGENCY_NET_STOP:return 'EMERGENCY_NET_STOP'
    if gross<=STOP_LOSS:return 'PRICE_STOP_LOSS'
    if roi>=TAKE_PROFIT:return 'TAKE_PROFIT'
    if peak_roi is not None and peak_roi>=TRAIL_ARM and roi<=peak_roi-TRAIL_GAP:
        return 'TRAILING_STOP'
    if now-int(p['opened_at'])>=MAX_HOLD_SECONDS:return 'TIMEOUT_15M'
    return None

def eligible_candidates(c,candidates,now,excluded=None):
    if not isinstance(candidates,list):return []
    existing={p['address'] for p in c.execute('SELECT address FROM meme_eur_positions')}
    existing.update(excluded or ())
    ranked=[]
    seen=set()
    for t in candidates[:30]:
        if not isinstance(t,dict):continue
        address=t.get('address')
        if (not isinstance(address,str) or not ADDRESS.fullmatch(address)
                or address in existing or address in seen):continue
        seen.add(address)
        price=_number(t.get('price_usd'))
        liq=_number(t.get('liquidity_usd'))
        vol=_number(t.get('volume_24h_usd'))
        if not price or liq is None or liq<MIN_AUTO_LIQUIDITY or vol is None or vol<MIN_AUTO_VOLUME:continue
        previous=c.execute('SELECT MAX(timestamp) FROM meme_eur_trades WHERE address=?',(address,)).fetchone()[0]
        if previous is not None and now-int(previous)<COOLDOWN_SECONDS:continue
        ranked.append((liq,vol,t))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
    return [t for _,_,t in ranked]

def choose_candidate(c,candidates,now,exclude=None):
    choices=eligible_candidates(c,candidates,now,exclude)
    return choices[0] if choices else None

def tick(c,now=None,scout=scan,quote=indicative_quote,fx_rate=get_fx,force_scan=False):
    """One cycle. Caller holds server mutex; all fills remain virtual."""
    now=int(time.time()) if now is None else int(now)
    init_auto(c)
    a=c.execute('SELECT * FROM meme_auto_state WHERE id=1').fetchone()
    if not a['enabled']:return status(c)
    messages=[]
    fx=None
    try:
        fx=fx_rate(c,now=now)
    except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
        messages.append('CAMBIO_USD_EUR_NON_DISPONIBILE '+type(exc).__name__)
    c.execute('DELETE FROM meme_auto_trail WHERE address NOT IN (SELECT address FROM meme_eur_positions)')
    positions=[dict(p) for p in c.execute('SELECT * FROM meme_eur_positions ORDER BY opened_at')]
    if fx is not None:
        for pos in positions[:MAX_POSITIONS]:
            addr=pos['address']
            try:
                q=quote(addr)
                price=_number(q.get('price_usd'))
                if price is None or price<=0:raise ValueError('Quotazione non valida')
                mark(c,addr,q,fx,now=now)
                # Publish meaningful actual quote observations, not artificial ticks.
                # Throttle unchanged quotes; no claim of tradable fills.
                previous_price=_number(pos.get('last_price_usd'))
                prev_time=int(pos.get('last_checked_at') or 0)
                if (previous_price is not None and previous_price>0 and
                    price!=previous_price and now-prev_time>=10):
                    pct=(price/previous_price-1)*100
                    if abs(pct)>=0.2:
                        _log(c,now,addr,'PRICE_OBSERVED',
                             'Prezzo USD '+format(price,'.12g')+
                             ' · variazione dal controllo precedente '+
                             format(pct,'+.2f')+'% · quota REST indicativa')
                roi=net_roi(pos,price,fx['usd_eur'])
                old=c.execute('SELECT peak_net_roi FROM meme_auto_trail WHERE address=?',(addr,)).fetchone()
                peak=max(roi,float(old['peak_net_roi'])) if old else roi
                c.execute('''INSERT INTO meme_auto_trail(address,peak_net_roi,updated_at)
                    VALUES(?,?,?) ON CONFLICT(address) DO UPDATE SET
                    peak_net_roi=excluded.peak_net_roi,updated_at=excluded.updated_at''',
                    (addr,peak,now))
                reason=decide_exit(pos,price,now,fx['usd_eur'],peak_roi=peak)
                if reason:
                    result=trade(c,addr,'SELL',q,fx,now=now)
                    c.execute('DELETE FROM meme_auto_trail WHERE address=?',(addr,))
                    _log(c,now,addr,'AUTO_SELL',reason+' · P/L netto virtuale € '+
                         str(result['pnl_eur'])+' · prezzi indicativi, esecuzione non verificata')
                    messages.append('AUTO_SELL '+reason)
            except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
                messages.append('QUOTE_NON_DISPONIBILE '+type(exc).__name__)
    if force_scan or now-int(a['last_scan'])>=SCAN_SECONDS:
        c.execute('UPDATE meme_auto_state SET last_scan=? WHERE id=1',(now,))
        if fx is None:
            messages.append('SCAN_SOSPESO_SENZA_CAMBIO')
            _log(c,now,None,'AUTO_ERROR','Scansione sospesa: cambio USD/EUR indisponibile')
        else:
            try:
                report=scout()
                rows=report.get('candidates',[]) if isinstance(report,dict) else []
                count=c.execute('SELECT COUNT(*) FROM meme_eur_positions').fetchone()[0]
                bought=0
                candidates=eligible_candidates(c,rows,now)
                guard=circuit_breaker(c,now)
                if guard['blocked']:
                    from meme_intelligence import observe_blocked
                    observed=observe_blocked(c,rows,now=now)
                    # Observations reuse the already obtained scout snapshot.
                    # Never place orders or consult paid models for blocked entries.
                    if observed:
                        messages.append('WATCHLIST_'+str(observed)+'_OSSERVATI')
                    candidates=[]
                    _log(c,now,None,'RISK_CIRCUIT',
                         'Nuovi ingressi SOSPESI · '+guard['reason']+
                         ' · drawdown '+str(guard.get('drawdown_pct','N/D'))+
                         '% · soglia '+str(MAX_EQUITY_DRAWDOWN*100)+
                         '% · uscite PAPER ancora attive')
                    messages.append('RISCHIO_STOP_NUOVI_ACQUISTI')
                # Do not spend paid model calls again on identical candidates
                # before five minutes; cached verdicts do not bypass risk gates.
                agent_row=c.execute('SELECT updated_at,report_json FROM meme_agent_latest WHERE id=1').fetchone()
                addresses=[t['address'] for t in candidates[:3]]
                cached=json.loads(agent_row['report_json']) if agent_row else None
                reuse=(cached is not None and now-int(agent_row['updated_at'])<300 and
                       cached.get('reviewed_addresses')==addresses)
                if reuse:
                    assessment=cached
                    _log(c,now,None,'AGENT_CACHE',
                         'Riutilizzata valutazione precedente per candidati invariati · '
                         'nessun nuovo consulto API')
                else:
                    if guard['blocked']:
                        from meme_agents import rule_agents
                        assessment=rule_agents([])
                        assessment['note']='Solo osservazione: RISK Circuit Breaker attivo; nessuna consultazione IA'
                    else:
                        assessment=review_meme_agents(candidates[:3])
                    c.execute('''INSERT INTO meme_agent_latest(id,updated_at,report_json)
                        VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET
                        updated_at=excluded.updated_at,report_json=excluded.report_json''',
                        (now,json.dumps(assessment,ensure_ascii=False)))
                    _log(c,now,None,'AI_DESK',
                         assessment['mode']+' · '+assessment['status']+' · '+
                         str(len(assessment['approved_addresses']))+' candidati senza veto · '+
                         assessment['note'])
                    for agent in assessment['agents']:
                        _log(c,now,None,'AGENT_'+agent['name'].replace(' ','_'),
                             agent['status']+' · '+agent['reason'])
                candidates=[t for t in candidates if
                            t['address'] in assessment['approved_addresses']]
                if not rows:
                    messages.append('SCOUT_SENZA_TOKEN')
                elif not candidates:
                    messages.append('0_IDONEI_SU_'+str(len(rows))+'_TOKEN')
                else:
                    messages.append(str(len(candidates))+'_IDONEI_SU_'+str(len(rows))+'_TOKEN')
                for candidate in candidates:
                    if bought>=MAX_ENTRIES_PER_SCAN or count>=MAX_POSITIONS:break
                    mint=candidate['address']
                    try:
                        q=quote(mint)
                        p=_number(q.get('price_usd'))
                        liquidity=_number(q.get('liquidity_usd'))
                        volume=_number(q.get('volume_24h_usd'))
                        if (not p or liquidity is None or liquidity<MIN_AUTO_LIQUIDITY
                                or volume is None or volume<MIN_AUTO_VOLUME):
                            messages.append('CANDIDATO_QUOTE_NON_IDONEA')
                            continue
                        rejection=entry_rejection(candidate,q)
                        if rejection:
                            _log(c,now,mint,'AUTO_REJECT',
                                 rejection+' · liquidita min USD '+str(int(MIN_ENTRY_LIQUIDITY))+
                                 ' · volume 24h min USD '+str(int(MIN_ENTRY_VOLUME))+
                                 ' · nessun acquisto')
                            messages.append('FILTRO_QUALITA_'+rejection)
                            continue
                        stake=dynamic_stake(c,candidate,q)
                        if stake is None:
                            messages.append('CAPITALE_DISPONIBILE_O_RISERVA_INSUFFICIENTE')
                            break
                        result=trade(c,mint,'BUY',q,fx,now=now,stake_eur=stake)
                        _log(c,now,mint,'AUTO_BUY','Entrata virtuale EUR '+str(result['cost_eur'])+
                             ' · liquidita USD '+str(round(liquidity))+
                             ' · volume 24h USD '+str(round(volume))+
                             ' · vendibilita non verificata')
                        bought+=1
                        count+=1
                        messages.append('AUTO_BUY '+mint[:8])
                    except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
                        messages.append('CANDIDATO_NON_DISPONIBILE '+type(exc).__name__)
                _log(c,now,None,'AUTO_SCAN',
                     'Analizzati '+str(len(rows))+' token; '+str(len(candidates))+
                     ' idonei; '+str(bought)+' acquisti virtuali; '+
                     str(count)+' posizioni in portafoglio')
                if count>=MAX_POSITIONS:messages.append('LIMITE_POSIZIONI')
                elif bought==0 and not any(x.startswith('CANDIDATO_') for x in messages):
                    messages.append('NESSUN_CANDIDATO_IDONEO')
            except (OSError,TypeError,ValueError,KeyError,OverflowError,TimeoutError) as exc:
                messages.append('SCOUT_NON_DISPONIBILE '+type(exc).__name__)
                _log(c,now,None,'AUTO_ERROR','Scout non disponibile: '+type(exc).__name__)
    label=' · '.join(messages) if messages else 'MONITORAGGIO'
    errors=[m for m in messages if 'NON_DISPONIBILE' in m or 'SOSPESO_SENZA' in m]
    c.execute('UPDATE meme_auto_state SET last_tick=?,last_status=?,last_error=? WHERE id=1',
              (now,label[:250],'; '.join(errors)[:250]))
    c.commit()
    return status(c)
