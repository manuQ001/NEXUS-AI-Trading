"""Offline contract tests for live profile discovery; no external network."""
import json
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from meme_live import ProfileInbox,_receive,_send_frame,MAX_FRAME
from meme_scout import scan_profiles,PAIRS_ROOT

A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
def row(address):return {'chainId':'solana','tokenAddress':address}

class DummySocket:
    def __init__(self,received=b''):
        self.received=bytearray(received)
        self.sent=b''
    def recv(self,n):
        part=bytes(self.received[:n])
        del self.received[:n]
        return part
    def sendall(self,payload):
        self.sent+=payload

class TestProfileStream(unittest.TestCase):
    def test_first_snapshot_is_baseline_not_fake_launch(self):
        inbox=ProfileInbox()
        self.assertEqual(inbox.ingest({'data':[row(A)]},now=100),0)
        self.assertTrue(inbox.state()['bootstrapped'])
        self.assertEqual(inbox.state()['new_profiles'],0)
        self.assertEqual(inbox.pop(),[])
        self.assertEqual(inbox.ingest({'data':[row(A),row(B)]},now=105),1)
        self.assertEqual(inbox.pop(),[row(B)])
        self.assertEqual(inbox.ingest({'data':[row(B)]},now=107),0)
    def test_filters_other_chains_and_invalid_address(self):
        inbox=ProfileInbox()
        inbox.ingest([],now=100)
        bad=[{'chainId':'ethereum','tokenAddress':B},row('not-a-mint')]
        self.assertEqual(inbox.ingest({'data':bad},now=120),0)
        self.assertEqual(inbox.pop(),[])
    def test_live_batch_must_enrich_observed_pairs_before_auto(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            return [{'chainId':'solana','baseToken':{'address':B,'symbol':'XYZ'},
                     'priceUsd':'0.01','liquidity':{'usd':800},
                     'volume':{'h24':1300},'txns':{'h24':{'buys':2,'sells':3}}}]
        report=scan_profiles([row(B)],fetch=fetch)
        self.assertEqual(calls,[PAIRS_ROOT+B])
        self.assertEqual(report['candidates'][0]['address'],B)
        self.assertFalse(report['candidates'][0]['trade_authorized'])
    def test_non_solana_pair_cannot_be_approved(self):
        report=scan_profiles([row(B)],fetch=lambda url:[
            {'chainId':'ethereum','baseToken':{'address':B},
             'priceUsd':'1','liquidity':{'usd':10000}}])
        self.assertEqual(report['candidates'],[])
    def test_ws_text_frame_and_ping(self):
        packet=b'hello'
        sock=DummySocket(bytes([0x81,len(packet)])+packet)
        self.assertEqual(_receive(sock),packet)
        sock=DummySocket(bytes([0x89,3])+b'hey')
        self.assertIsNone(_receive(sock))
        self.assertEqual(sock.sent[0]&15,10)  # masked client pong
        self.assertTrue(sock.sent[1]&128)
    def test_oversized_payload_rejected_before_allocation(self):
        sock=DummySocket(bytes([0x81,127])+struct.pack('!Q',MAX_FRAME+1))
        with self.assertRaises(ValueError):_receive(sock)

if __name__=='__main__':unittest.main()
