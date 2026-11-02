"""Decode a bounded-latency FYERS index snapshot; tt is a session date, not tick time."""
import math


def decode_spot(result, started, received):
    if not 0 <= received - started <= 2 or result.get('s') != 'ok':
        return None
    for row in result.get('d', []):
        if row.get('n') != 'NSE:NIFTY50-INDEX' or row.get('s') != 'ok':
            continue
        try:
            price = float(row['v']['lp'])
        except (KeyError, ValueError, TypeError):
            continue
        if math.isfinite(price) and price > 0:
            return {'symbol': row['n'], 'ltp': price, 'at': received,
                    'timestampBasis': 'received', 'source': 'FYERS REST snapshot',
                    'bid': 0, 'ask': 0, 'bid_qty': 0, 'ask_qty': 0}
    return None
