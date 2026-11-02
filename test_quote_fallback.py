import unittest
from quote_fallback import decode_spot


class SnapshotTests(unittest.TestCase):
    def result(self, price=22500):
        return {'s': 'ok', 'd': [{'s': 'ok', 'n': 'NSE:NIFTY50-INDEX',
                                'v': {'lp': price, 'tt': '1792713600'}}]}

    def test_snapshot_labels_receipt_time_and_does_not_invent_depth(self):
        q = decode_spot(self.result(), 100, 100.2)
        self.assertEqual(q['at'], 100.2)
        self.assertEqual(q['timestampBasis'], 'received')
        self.assertEqual(q['source'], 'FYERS REST snapshot')
        self.assertEqual(q['bid_qty'], 0)

    def test_delayed_error_and_invalid_prices_rejected(self):
        self.assertIsNone(decode_spot(self.result(), 100, 103))
        self.assertIsNone(decode_spot({'s': 'error'}, 100, 100.1))
        for price in (0, -1, float('nan'), float('inf'), None):
            self.assertIsNone(decode_spot(self.result(price), 100, 100.1))


if __name__ == '__main__':
    unittest.main()
