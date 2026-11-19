"""Unit tests for browser-independent paper-only market monitoring."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import server


class StopAfterOne:
    def __init__(self):
        self.wait_calls=[]
    def is_set(self):
        return False
    def wait(self,seconds):
        self.wait_calls.append(seconds)
        return True


class TestMarketMonitor(unittest.TestCase):
    def test_worker_refreshes_independently_of_browser(self):
        stop=StopAfterOne()
        fake=MagicMock()
        with patch('server.connect',return_value=fake) as connection, \
             patch('server.refresh',return_value={'BTC':'OK','ETH':'OK'}) as refresh, \
             patch('server.time.time',return_value=1800000000):
            server.market_monitor_loop(stop)
        connection.assert_called_once()
        refresh.assert_called_once_with(fake)
        fake.close.assert_called_once()
        self.assertEqual(stop.wait_calls,[30])
        self.assertEqual(server.MONITOR['last_success'],1800000000)
        self.assertEqual(server.MONITOR['status'],{'BTC':'OK','ETH':'OK'})
    def test_worker_survives_transient_error(self):
        stop=StopAfterOne()
        fake=MagicMock()
        with patch('server.connect',return_value=fake), \
             patch('server.refresh',side_effect=OSError('offline')), \
             patch('server.time.time',return_value=1800000001), \
             patch('builtins.print'):
            server.market_monitor_loop(stop)
        fake.close.assert_called_once()
        self.assertEqual(server.MONITOR['error'],'Monitor: OSError')
        self.assertEqual(stop.wait_calls,[30])
    def test_worker_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            server.market_monitor_loop(StopAfterOne(),interval_seconds=0)
    def test_worker_obeys_stop_before_request(self):
        stop=MagicMock()
        stop.is_set.return_value=True
        with patch('server.connect') as connection:
            server.market_monitor_loop(stop)
        connection.assert_not_called()


if __name__=='__main__':
    unittest.main()
