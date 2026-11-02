import struct
import unittest
from types import SimpleNamespace
from fyers_sdk_compat import install
from fyers_apiv3.FyersWebsocket.data_ws import FyersDataSocket


class IndexDeltaTests(unittest.TestCase):
    def test_unchanged_fields_keep_last_price_and_exchange_timestamp(self):
        install()
        row = {'ltp': 2242655, 'prev_close_price': 2250000,
               'exch_feed_time': 1792737268}
        emitted = []
        decoder = SimpleNamespace(
            ack_count=0, index_sym={7: 'if|nifty'}, scrips_sym={}, dp_sym={},
            index_val=['ltp', 'prev_close_price', 'exch_feed_time'],
            resp={'if|nifty': row}, data_logger=SimpleNamespace(
                exception=lambda exc: self.fail(str(exc))))
        decoder._FyersDataSocket__response_output = lambda row, kind: emitted.append(dict(row))
        decode = FyersDataSocket._FyersDataSocket__datafeed_resp
        def packet(values):
            return b'\0' * 7 + struct.pack('!H', 1) + b'U' + struct.pack('H', 7) + bytes([3]) + struct.pack('>iii', *values)
        decode(decoder, packet([2242700, -2147483648, -2147483648]))
        self.assertEqual(row['ltp'], 2242700)
        self.assertEqual(row['exch_feed_time'], 1792737268)
        self.assertEqual(row['prev_close_price'], 2250000)
        self.assertEqual(len(emitted), 1)
        decode(decoder, packet([-2147483648, -2147483648, 1792737269]))
        self.assertEqual(row['ltp'], 2242700)
        self.assertEqual(row['exch_feed_time'], 1792737269)
        decode(decoder, packet([-2147483648] * 3))
        self.assertEqual(len(emitted), 2)


if __name__ == '__main__':
    unittest.main()
