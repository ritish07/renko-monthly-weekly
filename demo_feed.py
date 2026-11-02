"""Explicitly synthetic local UI demo. Never contacts a broker."""
import json
import math
import sys
import time
from datetime import datetime,timedelta,timezone
IST=timezone(timedelta(hours=5,minutes=30))
now=datetime.now(IST);date=now.date().isoformat();expiry=(now+timedelta(days=7)).date().isoformat()
contracts=[dict(symbol=f'DEMO:{strike}{side}',strike=strike,lotSize=65,expiry=expiry,type=side)
           for strike in range(23000,25001,50) for side in ('CE','PE')]
print('DATA '+json.dumps(dict(kind='master',day=date,contracts=contracts,holidays=[])),flush=True)
started=time.time()
while True:
    t=time.time();spot=24000+150*math.sin((t-started)/12)
    ticks=[dict(symbol='NSE:NIFTY50-INDEX',ltp=spot,at=t,timestampBasis='received',source='SYNTHETIC DEMO')]
    for c in contracts:
        intrinsic=max(0,spot-c['strike']) if c['type']=='CE' else max(0,c['strike']-spot)
        premium=round(80+intrinsic,2)
        ticks.append(dict(symbol=c['symbol'],ltp=premium,at=t,bid=premium-.25,ask=premium+.25,bid_qty=6500,ask_qty=6500))
    print('DATA '+json.dumps(dict(kind='ticks',broker='DEMO',ticks=ticks,lost=False,transport=True,
        authenticated=True,market_open=True,at=t,error=None)),flush=True)
    time.sleep(.25)
