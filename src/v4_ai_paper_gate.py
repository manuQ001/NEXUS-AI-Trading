"""Read-only AI consensus gate for V4 PAPER entries.

AI cannot create orders, override Python, lift a risk lock, or initiate an exit.
Disabled by default; missing/stale reviews fail closed when enabled.
"""
import os

MAX_AI_AGE_SECONDS=300
MAX_QUOTE_DRIFT_SECONDS=300

def enabled(env=None):
    env=os.environ if env is None else env
    return env.get('NEXUS_V4_AI_PAPER_GATE','0')=='1'

def approve_entry(c,address,quote_observed_at,now,env=None):
    """Return (approved, reason). Never treats a missing opinion as BUY."""
    if not enabled(env):
        return True,'AI_GATE_DISABLED'
    row=c.execute("""SELECT timestamp,observed_at,verdict,outcome
        FROM v4_ai_shadow_audit WHERE address=?
        ORDER BY id DESC LIMIT 1""",(address,)).fetchone() if c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v4_ai_shadow_audit'"
        ).fetchone() else None
    if row is None:
        return False,'AI_NO_REVIEW'
    if row['outcome']!='COMPLETED':
        return False,'AI_NOT_COMPLETED'
    if row['verdict']!='BUY':
        return False,'AI_'+str(row['verdict'] or 'NO_VERDICT')[:30]
    age=int(now)-int(row['timestamp'])
    if age<0 or age>MAX_AI_AGE_SECONDS:
        return False,'AI_STALE'
    observed=int(quote_observed_at)
    basis=int(row['observed_at'])
    if observed<basis or observed-basis>MAX_QUOTE_DRIFT_SECONDS:
        return False,'AI_QUOTE_NOT_MATCHED'
    return True,'AI_BUY_CONFIRMED'
