"""NEXUS 4.4 — AI can only veto PAPER entries, never force them."""
import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from v4_ai_paper_gate import approve_entry

MINT='sample-mint'

class TestPaperGate(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.row_factory=sqlite3.Row
        self.c.execute("""CREATE TABLE v4_ai_shadow_audit(
          id INTEGER PRIMARY KEY,timestamp INTEGER,observed_at INTEGER,
          address TEXT,verdict TEXT,outcome TEXT)""")
        self.env={'NEXUS_V4_AI_PAPER_GATE':'1'}

    def tearDown(self):self.c.close()

    def insert(self,verdict='BUY',outcome='COMPLETED',t=1000,obs=990):
        self.c.execute("""INSERT INTO v4_ai_shadow_audit
            (timestamp,observed_at,address,verdict,outcome) VALUES(?,?,?,?,?)""",
            (t,obs,MINT,verdict,outcome))

    def test_disabled_is_backward_compatible(self):
        self.assertEqual(approve_entry(self.c,MINT,1010,1030,{}),
                         (True,'AI_GATE_DISABLED'))

    def test_no_review_fails_closed(self):
        self.assertEqual(approve_entry(self.c,MINT,1010,1030,self.env),
                         (False,'AI_NO_REVIEW'))

    def test_fresh_buy_can_approve_only_matching_mint(self):
        self.insert()
        self.assertEqual(approve_entry(self.c,MINT,1010,1030,self.env),
                         (True,'AI_BUY_CONFIRMED'))
        self.assertFalse(approve_entry(self.c,'another',1010,1030,self.env)[0])

    def test_wait_sell_error_and_latest_review_veto(self):
        self.insert()
        self.insert('WAIT')
        self.assertEqual(approve_entry(self.c,MINT,1010,1030,self.env),
                         (False,'AI_WAIT'))
        self.insert('SELL')
        self.assertEqual(approve_entry(self.c,MINT,1010,1030,self.env),
                         (False,'AI_SELL'))
        self.insert('BUY','ERROR')
        self.assertEqual(approve_entry(self.c,MINT,1010,1030,self.env),
                         (False,'AI_NOT_COMPLETED'))

    def test_stale_future_and_unmatched_quote_fail(self):
        self.insert()
        self.assertEqual(approve_entry(self.c,MINT,1010,1400,self.env),
                         (False,'AI_STALE'))
        self.assertEqual(approve_entry(self.c,MINT,1010,900,self.env),
                         (False,'AI_STALE'))
        self.assertEqual(approve_entry(self.c,MINT,800,1030,self.env),
                         (False,'AI_QUOTE_NOT_MATCHED'))
        self.assertEqual(approve_entry(self.c,MINT,1300,1300,self.env),
                         (False,'AI_QUOTE_NOT_MATCHED'))

if __name__=='__main__':unittest.main()
