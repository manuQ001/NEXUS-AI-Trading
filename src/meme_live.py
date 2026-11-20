"""Event-driven DEX Screener token-profile discovery, PAPER only.

This is a profile-list WebSocket, NOT all new Solana mints or a price feed.
Stdlib RFC6455 client, TLS verified, bounded frames, reconnect & dedup.
No orders, private keys, or external writes. Fallback periodic REST scanner.
"""
import base64
from collections import deque
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time
from urllib.parse import urlparse
from meme_scout import ADDRESS

STREAM_URL='wss://api.dexscreener.com/token-profiles/latest/v1'
MAX_FRAME=256000
MAX_QUEUE=90
MAX_SEEN=1200
MAX_BATCH=30

class ProfileInbox:
    def __init__(self):
        self.lock=threading.Lock()
        self.pending=deque(maxlen=MAX_QUEUE)
        self.pending_addresses=set()
        self.seen=set()
        self.seen_order=deque()
        self.bootstrapped=False
        self.connected=False
        self.last_message=0
        self.last_profile=0
        self.received=0
        self.discovered=0
        self.last_error=''
        self.reconnects=0

    def ingest(self,payload,now=None):
        """Initial snapshot establishes baseline, never fake 'new' alerts."""
        now=int(time.time()) if now is None else int(now)
        rows=payload.get('data') if isinstance(payload,dict) else payload
        if not isinstance(rows,list):return 0
        valid=[]
        for item in rows[:MAX_SEEN]:
            if not isinstance(item,dict) or item.get('chainId')!='solana':continue
            address=item.get('tokenAddress')
            if isinstance(address,str) and ADDRESS.fullmatch(address):
                valid.append({'chainId':'solana','tokenAddress':address})
        new=0
        with self.lock:
            self.last_message=now
            self.received+=1
            for item in valid:
                address=item['tokenAddress']
                if address in self.seen:continue
                self.seen.add(address)
                self.seen_order.append(address)
                while len(self.seen_order)>MAX_SEEN:
                    self.seen.discard(self.seen_order.popleft())
                if not self.bootstrapped:continue
                if address not in self.pending_addresses:
                    if len(self.pending)==MAX_QUEUE:
                        old=self.pending.popleft()
                        self.pending_addresses.discard(old['tokenAddress'])
                    self.pending.append(item)
                    self.pending_addresses.add(address)
                    self.last_profile=now
                    self.discovered+=1
                    new+=1
            self.bootstrapped=True
        return new

    def pop(self,max_items=MAX_BATCH):
        result=[]
        with self.lock:
            while self.pending and len(result)<max_items:
                item=self.pending.popleft()
                self.pending_addresses.discard(item['tokenAddress'])
                result.append(item)
        return result

    def state(self):
        with self.lock:
            return {'source':'DEX Screener WebSocket token profiles, NOT Solana mint stream',
                    'connected':self.connected,'bootstrapped':self.bootstrapped,
                    'last_message':self.last_message,'last_new_profile':self.last_profile,
                    'messages':self.received,'new_profiles':self.discovered,
                    'queued':len(self.pending),'last_error':self.last_error,
                    'reconnects':self.reconnects,'price_stream':False,
                    'mode':'PROFILE_WS_DISCOVERY_PAPER_ONLY'}

INBOX=ProfileInbox()

def _read_exact(sock,n):
    chunks=[]
    while n:
        chunk=sock.recv(n)
        if not chunk:raise ConnectionError('WebSocket connection closed')
        chunks.append(chunk)
        n-=len(chunk)
    return b''.join(chunks)

def _send_frame(sock,opcode,payload=b''):
    # Client frames MUST be masked.
    if len(payload)>125 and opcode>=8:raise ValueError('Control frame too long')
    mask=os.urandom(4)
    header=bytes([0x80|opcode])
    if len(payload)<126:header+=bytes([0x80|len(payload)])
    elif len(payload)<65536:header+=bytes([0x80|126])+struct.pack('!H',len(payload))
    else:header+=bytes([0x80|127])+struct.pack('!Q',len(payload))
    masked=bytes(b ^ mask[i%4] for i,b in enumerate(payload))
    sock.sendall(header+mask+masked)

def _receive(sock):
    header=_read_exact(sock,2)
    fin=bool(header[0]&128)
    opcode=header[0]&15
    masked=bool(header[1]&128)
    length=header[1]&127
    if length==126:length=struct.unpack('!H',_read_exact(sock,2))[0]
    elif length==127:length=struct.unpack('!Q',_read_exact(sock,8))[0]
    if length>MAX_FRAME:raise ValueError('Oversize WS frame')
    if masked:mask=_read_exact(sock,4)
    payload=_read_exact(sock,length)
    if masked:payload=bytes(b ^ mask[i%4] for i,b in enumerate(payload))
    if opcode==9:
        _send_frame(sock,10,payload)
        return None
    if opcode==10:return None
    if opcode==8:raise ConnectionError('WebSocket server closed stream')
    if not fin or opcode!=1:raise ValueError('Unsupported fragmented or binary WS data')
    return payload

def _connect(timeout=12,target=STREAM_URL):
    url=urlparse(target)
    if url.scheme!='wss' or url.hostname not in ('api.dexscreener.com','pumpportal.fun') or url.port is not None or url.username or url.password:
        raise ValueError('Unexpected WebSocket destination')
    raw=socket.create_connection((url.hostname,443),timeout=timeout)
    try:
        sock=ssl.create_default_context().wrap_socket(raw,server_hostname=url.hostname)
        sock.settimeout(timeout)
        nonce=base64.b64encode(os.urandom(16)).decode('ascii')
        req=(f'GET {url.path} HTTP/1.1\r\nHost: {url.hostname}\r\n'
             'Upgrade: websocket\r\nConnection: Upgrade\r\n'
             f'Sec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n'
             'User-Agent: NEXUS-Paper-Profile-Scanner/3.3\r\n\r\n')
        sock.sendall(req.encode('ascii'))
        response=bytearray()
        while b'\r\n\r\n' not in response:
            if len(response)>8192:raise ValueError('Invalid WS handshake')
            chunk=sock.recv(1)
            if not chunk:raise ConnectionError('WS handshake closed')
            response.extend(chunk)
        raw_headers=response.decode('latin1').split('\r\n')
        if raw_headers[0].strip()!='HTTP/1.1 101 Switching Protocols':
            raise ConnectionError('WS upgrade rejected')
        headers={}
        for line in raw_headers[1:]:
            if ':' in line:
                a,b=line.split(':',1)
                headers[a.strip().lower()]=b.strip()
        expected=base64.b64encode(hashlib.sha1(
            (nonce+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if (headers.get('sec-websocket-accept')!=expected or
            headers.get('upgrade','').lower()!='websocket' or
            'upgrade' not in headers.get('connection','').lower()):
            raise ConnectionError('Invalid WS authentication response')
        return sock
    except Exception:
        try:sock.close()
        except (NameError,Exception):raw.close()
        raise

def listen(stop,inbox=INBOX,connect=_connect):
    """Dedicated daemon; never touches the database or purchases tokens."""
    backoff=2
    while not stop.is_set():
        sock=None
        try:
            sock=connect()
            with inbox.lock:
                inbox.connected=True
                inbox.last_error=''
            backoff=2
            while not stop.is_set():
                try:raw=_receive(sock)
                except socket.timeout:
                    # Avoid infinite stale 'connected' status when provider goes quiet.
                    _send_frame(sock,9,b'ping')
                    continue
                if raw is None:continue
                if len(raw)>MAX_FRAME:raise ValueError('WS message too long')
                try:data=json.loads(raw.decode('utf-8'))
                except (UnicodeError,ValueError):continue
                inbox.ingest(data)
        except (OSError,ConnectionError,ValueError,TimeoutError) as exc:
            with inbox.lock:
                inbox.last_error=type(exc).__name__
                inbox.reconnects+=1
        finally:
            if sock is not None:sock.close()
            with inbox.lock:
                inbox.connected=False
        if stop.wait(backoff):break
        backoff=min(60,backoff*2)
