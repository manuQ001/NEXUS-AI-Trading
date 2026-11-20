"""Real on-chain-creation *provider* stream, read-only; PumpPortal new mints.

No key, wallet, paid trade subscription or swaps. A provider message is not
independent blockchain confirmation; Solana mint metadata is untrusted.
The queue is visualization-only and never bypasses token risk gates.
"""
from collections import deque
import json
import socket
import threading
import time
from meme_live import _connect,_receive,_send_frame
from meme_scout import ADDRESS

URL='wss://pumpportal.fun/api/data'
MAX_RECENT=50
MAX_SEEN=3000
MAX_NAME=48

class MintFeed:
    def __init__(self):
        self.lock=threading.Lock()
        self.connected=False
        self.last_message=0
        self.last_mint=0
        self.received=0
        self.mints=0
        self.reconnects=0
        self.last_error=''
        self.seen=set()
        self.seen_order=deque()
        self.recent=deque(maxlen=MAX_RECENT)
        self.serial=0

    def ingest(self,payload,now=None):
        now=int(time.time()) if now is None else int(now)
        if not isinstance(payload,dict):return None
        # Reject provider notices / trades; only a token creation event.
        address=payload.get('mint')
        if not isinstance(address,str) or not ADDRESS.fullmatch(address):return None
        if payload.get('txType') not in ('create','CREATE'):return None
        with self.lock:
            self.last_message=now
            self.received+=1
            if address in self.seen:return None
            self.seen.add(address)
            self.seen_order.append(address)
            while len(self.seen_order)>MAX_SEEN:
                self.seen.discard(self.seen_order.popleft())
            self.serial+=1
            item={'id':self.serial,'mint':address,
                  'symbol':str(payload.get('symbol') or '?')[:MAX_NAME],
                  'name':str(payload.get('name') or '?')[:MAX_NAME],
                  'time':now,'kind':'PUMPPORTAL_NEW_MINT_OBSERVED',
                  'verified_on_chain':False,'trade_authorized':False}
            self.recent.append(item)
            self.last_mint=now
            self.mints+=1
            return dict(item)

    def state(self,limit=15):
        with self.lock:
            return {
                'source':'PumpPortal provider new-token events, not direct verified chain RPC',
                'connected':self.connected,'last_message':self.last_message,
                'last_mint':self.last_mint,'received':self.received,
                'mints':self.mints,'reconnects':self.reconnects,
                'last_error':self.last_error,
                'recent':[dict(x) for x in list(self.recent)[-max(0,min(30,int(limit))):]][::-1],
                'mode':'READ_ONLY_NEW_MINT_STREAM',
                'trade_authorized':False,'price_stream':False
            }

FEED=MintFeed()

def listen(stop,feed=FEED,connect=None,publish=None):
    """One provider WS with exponential reconnect; no DB writes and no trade API."""
    backoff=2
    while not stop.is_set():
        sock=None
        try:
            sock=(connect or (lambda:_connect(target=URL)))()
            _send_frame(sock,1,json.dumps({'method':'subscribeNewToken'}).encode('utf-8'))
            with feed.lock:
                feed.connected=True
                feed.last_error=''
            backoff=2
            while not stop.is_set():
                try:message=_receive(sock)
                except socket.timeout:
                    _send_frame(sock,9,b'ping')
                    continue
                if message is None:continue
                try:payload=json.loads(message.decode('utf-8'))
                except (ValueError,UnicodeError):continue
                item=feed.ingest(payload)
                if item and publish is not None:
                    publish('PAPER_MINT',{'id':item['id'],'mint':item['mint'],
                        'symbol':item['symbol'],'time':item['time'],
                        'source':'PumpPortal mint creation event; unverified'})
        except (OSError,ValueError,ConnectionError,TimeoutError) as exc:
            with feed.lock:
                feed.reconnects+=1
                feed.last_error=type(exc).__name__
        finally:
            if sock is not None:sock.close()
            with feed.lock:feed.connected=False
        if stop.wait(backoff):break
        backoff=min(backoff*2,60)
