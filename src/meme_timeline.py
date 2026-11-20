"""NEXUS 3.13: read-only decision timeline assembled from persisted local evidence.

No events are invented, and this module never inserts into wallet/order tables.
Returns short, source-labelled history for the live UI. The current risk lock
remains an independent and unchanged execution guard.
"""
import time

ALLOWED_JOURNAL={
    'AUTO_BUY':'ACQUISTO PAPER','AUTO_SELL':'VENDITA PAPER',
    'AUTO_SCAN':'SCAN MOTORE','AUTO_REJECT':'CANDIDATO SCARTATO',
    'RISK_CIRCUIT':'RISK LOCK','AI_DESK':'VALUTAZIONE AGENTI',
    'PRICE_OBSERVED':'PREZZO OSSERVATO',
}
MAX_ITEMS=36

def _exists(c,name):
    return bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone())

def timeline(c,now=None,limit=30):
    now=int(time.time()) if now is None else int(now)
    limit=max(1,min(int(limit),MAX_ITEMS))
    events=[]
    if _exists(c,'meme_auto_journal'):
        for r in c.execute("""SELECT id,timestamp,address,action,note
            FROM meme_auto_journal ORDER BY id DESC LIMIT 80"""):
            action=r['action']
            if action not in ALLOWED_JOURNAL:continue
            events.append({
                'key':'journal:'+str(r['id']),'source':'PAPER_JOURNAL',
                'category':'trade' if action in ('AUTO_BUY','AUTO_SELL') else
                           'risk' if action=='RISK_CIRCUIT' else 'decision',
                'timestamp':int(r['timestamp']),'title':ALLOWED_JOURNAL[action],
                'detail':str(r['note'] or '')[:220],
                'address':r['address'],'action':action,
                'paper_only':True,'verified_trade':False})
    if _exists(c,'meme_shadow_signals'):
        for r in c.execute("""SELECT id,symbol,address,created_at,evaluated_at,
            status,score,modeled_net_change_pct FROM meme_shadow_signals
            ORDER BY id DESC LIMIT 35"""):
            rid=str(r['id'])
            events.append({
                'key':'shadow:'+rid+':capture',
                'source':'SHADOW_SIGNAL','category':'shadow',
                'timestamp':int(r['created_at']),
                'title':'SHADOW · '+str(r['symbol'] or '?')[:24],
                'detail':'Score '+str(r['score'])+' · segnale teorico, nessun ordine',
                'address':r['address'],'action':'SIGNAL_CAPTURED',
                'paper_only':False,'verified_trade':False})
            if r['status'] in ('OBSERVED','INSUFFICIENT_DATA') and r['evaluated_at']:
                outcome=('Variazione netta teorica '+
                    format(float(r['modeled_net_change_pct']),'+.2f')+'%'
                    if r['status']=='OBSERVED' and
                       r['modeled_net_change_pct'] is not None
                    else 'Non valutabile: nessuna quota futura nel periodo')
                events.append({
                    'key':'shadow:'+rid+':result',
                    'source':'SHADOW_EVALUATION','category':'shadow',
                    'timestamp':int(r['evaluated_at']),
                    'title':'SHADOW · RISULTATO '+str(r['symbol'] or '?')[:24],
                    'detail':outcome+' · nessun ordine',
                    'address':r['address'],'action':str(r['status']),
                    'paper_only':False,'verified_trade':False})
    if _exists(c,'meme_scan_decisions'):
        for r in c.execute("""SELECT id,observed_at,address,symbol,decision,reason
            FROM meme_scan_decisions ORDER BY id DESC LIMIT 25"""):
            events.append({
                'key':'scan:'+str(r['id']),'source':'SCANNER',
                'category':'scan','timestamp':int(r['observed_at']),
                'title':'SCANNER · '+str(r['symbol'] or '?')[:24],
                'detail':str(r['decision'])+' · '+str(r['reason'] or '')[:145],
                'address':r['address'],'action':str(r['decision']),
                'paper_only':False,'verified_trade':False})
    events.sort(key=lambda e:(e['timestamp'],e['key']),reverse=True)
    selected=events[:limit]
    counts={}
    for e in selected:counts[e['category']]=counts.get(e['category'],0)+1
    return {'mode':'RECORDED_DECISIONS_ONLY','generated_at':now,
            'events':selected,'counts':counts,
            'total_returned':len(selected),
            'warning':('Timeline costruita da decisioni e osservazioni locali registrate. '
                'SHADOW non e una transazione. AUTO_BUY/SELL sono operazioni '
                'PAPER, non fill reali. Nessuna attivita generata artificialmente.')}
