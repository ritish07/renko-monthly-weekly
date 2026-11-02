from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
RULES = {
    "NIFTY": {"security_id": 13, "segment": "IDX_I", "fno": "NSE_FNO", "step": 50, "depth": 4, "target": 3.75, "vwap": True, "band": (80, 250)},
    "SENSEX": {"security_id": 51, "segment": "IDX_I", "fno": "BSE_FNO", "step": 100, "depth": 2, "target": 4.50, "vwap": True, "band": None},
    "BANKNIFTY": {"security_id": 25, "segment": "IDX_I", "fno": "NSE_FNO", "step": 100, "depth": 0, "target": 3.75, "vwap": True, "band": None},
}

def configured_rules(scope: str) -> dict:
    scope = scope.upper().strip()
    if scope not in ('ALL', 'NIFTY'):
        raise ValueError('VWAP_SCOPE must be ALL or NIFTY')
    return {asset: {**rule, 'vwap': scope == 'ALL' or asset == 'NIFTY'} for asset, rule in RULES.items()}

def positive(value) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False

def completed_session(candles: list[dict], now: datetime) -> list[dict]:
    """Validate current IST session bars and discard every unfinished bar."""
    if now.tzinfo is None:
        raise ValueError('A timezone-aware evaluation time is required')
    now = now.astimezone(IST)
    start = int(now.replace(hour=9, minute=15, second=0, microsecond=0).timestamp())
    end = start + 375 * 60
    unique = {}
    for raw in candles:
        timestamp = float(raw['timestamp'])
        if not math.isfinite(timestamp) or timestamp != int(timestamp) or timestamp % 60:
            raise ValueError('Invalid one-minute candle timestamp')
        timestamp = int(timestamp)
        if not start <= timestamp < end or timestamp + 60 > now.timestamp():
            continue
        values = {key: float(raw[key]) for key in ('open', 'high', 'low', 'close')}
        volume = float(raw.get('volume', 0))
        if not all(positive(value) for value in values.values()) or not math.isfinite(volume) or volume < 0:
            raise ValueError('Invalid candle price or volume')
        if values['low'] > min(values['open'], values['close']) or values['high'] < max(values['open'], values['close']):
            raise ValueError('Inconsistent candle OHLC')
        candle = {'timestamp': timestamp, **values, 'volume': volume}
        if timestamp in unique and unique[timestamp] != candle:
            raise ValueError('Conflicting duplicate candles')
        unique[timestamp] = candle
    return [unique[key] for key in sorted(unique)]

def underlying_context(candles: list[dict], signal_timestamp: int, now: datetime) -> dict | None:
    bars = [bar for bar in completed_session(candles, now) if bar['timestamp'] <= signal_timestamp]
    start = int(now.astimezone(IST).replace(hour=9, minute=15, second=0, microsecond=0).timestamp())
    # Missing minutes would make session VWAP incomplete. Never approximate it.
    expected = list(range(start, signal_timestamp + 1, 60))
    if [bar['timestamp'] for bar in bars] != expected or not bars:
        return None
    volume = sum(bar['volume'] for bar in bars)
    weighted = sum((bar['high'] + bar['low'] + bar['close']) / 3 * bar['volume'] for bar in bars)
    return {'timestamp': signal_timestamp, 'close': bars[-1]['close'],
            'vwap': weighted / volume if volume > 0 else None, 'volume': volume}

def half_up(value: float, step: int) -> int:
    return int(math.floor(value / step + .5) * step)

def level(day_open: float, multiplier: float) -> float:
    if not positive(day_open):
        raise ValueError('Invalid option day open')
    return round(day_open + multiplier * 2 * math.sqrt(day_open), 2)

def contract_strike(asset: str, spot: float, side: str) -> int:
    rule = RULES[asset]
    if not positive(spot) or side not in ('CE', 'PE'):
        raise ValueError('Invalid contract selection')
    atm = half_up(spot, rule['step'])
    return atm + (-rule['depth'] * rule['step'] if side == 'CE' else rule['depth'] * rule['step'])

def signal(asset: str, side: str, spot: float, vwap: float | None, candle: dict, day_open: float, rule: dict | None = None) -> dict | None:
    rule = rule or RULES[asset]
    if side not in ('CE', 'PE') or not positive(spot) or not positive(day_open):
        return None
    entry, stop, target = level(day_open, .75), level(day_open, -1.5), level(day_open, rule['target'])
    if not 0 < stop < entry < target:
        return None
    if not (float(candle['low']) <= entry <= float(candle['high'])):
        return None
    if rule['vwap'] and (not positive(vwap) or (side == 'CE' and spot <= vwap) or (side == 'PE' and spot >= vwap)):
        return None
    if rule['band'] and not (rule['band'][0] <= entry <= rule['band'][1]):
        return None
    return {'entry': entry, 'stop': stop, 'target': target, 'side': side}

def charges(exchange: str, buy: float, sell: float, quantity: int) -> dict:
    buy_turn, sell_turn = buy * quantity, sell * quantity
    turnover = buy_turn + sell_turn
    brokerage = 40.0
    transaction = turnover * (.0003503 if exchange == 'NSE' else .000325)
    sebi = turnover * .000001
    stamp = round(buy_turn * .00003)
    stt = round(sell_turn * .001)
    gst = (brokerage + transaction + sebi) * .18
    total = round(brokerage + transaction + sebi + stamp + stt + gst, 2)
    return {'brokerage': brokerage, 'transaction': transaction, 'sebi': sebi, 'stamp': stamp, 'stt': stt, 'gst': gst, 'total': total}
