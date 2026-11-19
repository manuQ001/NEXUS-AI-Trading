"""WHALE TRACKER 1.0 — read-only Solana token-account concentration.

Uses three bounded public JSON-RPC queries: getTokenSupply,
getTokenLargestAccounts, getMultipleAccounts(jsonParsed).
Largest TOKEN ACCOUNTS are not necessarily distinct wallets.
Pool custody, exchanges and owner identities are not independently verified.
NO BUY authority, wallet access, signatures, or order methods.
"""
import json
import re
import time
from urllib.request import Request, urlopen

RPC_URL = 'https://api.mainnet-beta.solana.com'
ADDRESS = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
MAX_BODY = 240000
MAX_U64 = 2**64 - 1
METHODS = {'getTokenSupply', 'getTokenLargestAccounts', 'getMultipleAccounts'}


def _rpc(method, params):
    if method not in METHODS:
        raise ValueError('Metodo RPC non consentito')
    raw = json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode('utf-8')
    req = Request(RPC_URL, data=raw, headers={
        'Content-Type':'application/json','Accept':'application/json',
        'User-Agent':'NEXUS-Read-Only-Whale/1.0'}, method='POST')
    with urlopen(req,timeout=8) as response:
        if response.status!=200:raise ValueError('RPC Solana non disponibile')
        blob=response.read(MAX_BODY+1)
    if len(blob)>MAX_BODY:raise ValueError('Risposta RPC troppo grande')
    obj=json.loads(blob)
    if not isinstance(obj,dict) or obj.get('error') is not None or not isinstance(obj.get('result'),dict):
        raise ValueError('Risposta Solana non valida')
    return obj['result']


def _amount(value):
    if not isinstance(value,str) or not value.isdecimal() or len(value)>20:
        raise ValueError('Importo token non valido')
    num=int(value)
    if num<0 or num>MAX_U64:raise ValueError('Importo token fuori intervallo')
    return num


def analyze(mint, supply_response, largest_response, owners_response=None, now=None):
    """Pure analyzer: percentages use raw base-unit amounts, never floats."""
    if not isinstance(mint,str) or not ADDRESS.fullmatch(mint):
        raise ValueError('Mint Solana non valido')
    if not isinstance(supply_response,dict) or not isinstance(largest_response,dict):
        raise ValueError('RPC dati mancanti')
    sup=supply_response.get('value')
    pool=largest_response.get('value')
    if not isinstance(sup,dict) or not isinstance(pool,list) or len(pool)>20:
        raise ValueError('Risposta RPC token non valida')
    total=_amount(sup.get('amount'))
    decimals=sup.get('decimals')
    if type(decimals) is not int or not 0<=decimals<=18 or total<=0:
        raise ValueError('Supply non disponibile o non valido')
    accounts=[]
    seen=set()
    for a in pool:
        if not isinstance(a,dict):raise ValueError('Token account malformato')
        addr=a.get('address')
        if not isinstance(addr,str) or not ADDRESS.fullmatch(addr) or addr in seen:
            raise ValueError('Account token non valido o duplicato')
        seen.add(addr)
        amount=_amount(a.get('amount'))
        if amount>total:raise ValueError('Bilancio superiore al supply')
        accounts.append({'address':addr,'amount_raw':str(amount),
                         'percentage_supply':round(100*amount/total,4),
                         'owner':None,'owner_classification':'NON_VERIFICATA'})
    accounts.sort(key=lambda a:int(a['amount_raw']),reverse=True)
    # A token account may be owned by a wallet, program, LP or custodian;
    # no unsupported classification or de-duplication claim is made.
    owner_data_valid=False
    if isinstance(owners_response,dict):
        values=owners_response.get('value')
        if isinstance(values,list) and len(values)==len(pool):
            extracted={}
            for original,account in zip(pool,values):
                info=((account or {}).get('data') or {}).get('parsed') if isinstance(account,dict) else None
                info=(info or {}).get('info') if isinstance(info,dict) else None
                owner=(info or {}).get('owner') if isinstance(info,dict) else None
                if isinstance(owner,str) and ADDRESS.fullmatch(owner):
                    extracted[original['address']]=owner
            owner_data_valid=len(extracted)==len(pool)
            for a in accounts:a['owner']=extracted.get(a['address'])
    owner_groups=[]
    if owner_data_valid:
        grouped={}
        for a in accounts:
            grouped[a['owner']]=grouped.get(a['owner'],0)+int(a['amount_raw'])
        owner_groups=[{'owner':owner,'percentage_supply_observed':round(100*amt/total,4),
                       'observed_token_accounts':sum(a['owner']==owner for a in accounts)}
                      for owner,amt in sorted(grouped.items(),key=lambda kv:kv[1],reverse=True)]
    top10=sum(int(a['amount_raw']) for a in accounts[:10])
    top20=sum(int(a['amount_raw']) for a in accounts)
    if top20>total:raise ValueError('Somma account superiore al supply')
    top10pct=100*top10/total
    flags=[]
    if top10pct>=60:flags.append('I primi 10 token account detengono almeno il 60% della supply')
    if not owner_data_valid:flags.append('Proprietari dei token account non verificati')
    flags.append('Account di pool, exchange e custodia NON identificati o esclusi')
    return {
        'ok':True,'mode':'READ_ONLY','chain':'solana','mint':mint,
        'source':'Solana mainnet JSON-RPC',
        'observed_at':int(time.time()) if now is None else int(now),
        'supply_raw':str(total),'decimals':decimals,
        'top10_token_accounts_pct':round(top10pct,4),
        'top20_token_accounts_pct':round(100*top20/total,4),
        'returned_token_accounts':len(accounts),
        'accounts':accounts[:10],
        'owners_resolved':owner_data_valid,
        'owner_groups_observed':owner_groups[:10],
        'warnings':flags,
        'liquidity_pool_excluded':False,
        'holders_count':'NON_DISPONIBILE',
        'status':'CONCENTRAZIONE_ELEVATA' if top10pct>=60 else 'SOLO_DISTRIBUZIONE_ACCOUNT',
        'trade_authorized':False,'meme_execution':'BLOCKED',
        'warning':'Percentuali riferite ai TOKEN ACCOUNT, non ai singoli wallet. Un proprietario può possedere più token account e un pool custodisce fondi di terzi. Proprietari osservati solo nel campione dei 20 account principali. Non sono identificati/esclusi pool o exchange. Snapshot RPC non atomici; dati non dimostrano sicurezza, vendibilità o liquidità bloccata.'
    }


def inspect(mint, rpc=_rpc):
    if not isinstance(mint,str) or not ADDRESS.fullmatch(mint):
        raise ValueError('Mint Solana non valido')
    supply=rpc('getTokenSupply',[mint,{'commitment':'confirmed'}])
    largest=rpc('getTokenLargestAccounts',[mint,{'commitment':'confirmed'}])
    list_of_accounts=largest.get('value')
    if not isinstance(list_of_accounts,list) or len(list_of_accounts)>20:
        raise ValueError('Lista account RPC non valida')
    addresses=[]
    for item in list_of_accounts:
        address=item.get('address') if isinstance(item,dict) else None
        if not isinstance(address,str) or not ADDRESS.fullmatch(address) or address in addresses:
            raise ValueError('Account token non valido')
        addresses.append(address)
    owners=None
    if addresses:
        try:
            owners=rpc('getMultipleAccounts',[addresses,{'encoding':'jsonParsed','commitment':'confirmed'}])
        except (OSError,ValueError,TypeError,KeyError,TimeoutError):
            # Concentration of token accounts can still be reported without
            # inventing wallet owners if the third endpoint is unavailable.
            owners=None
    return analyze(mint,supply,largest,owners)
