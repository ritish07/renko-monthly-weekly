"""Dedicated, read-only FYERS quotes. No order, position or funds API calls."""
import sys,os,json,time,threading,queue,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'vendor/fyers'))
from broker import Broker
from market_feed import MarketFeed
from datetime import datetime
from strategy import IST
from fyers_sdk_compat import install
from quote_fallback import decode_spot
install()
ROOT=Path(__file__).parent
CONFIG=json.loads((ROOT/'config.json').read_text())
HOLIDAYS=CONFIG['holidays']
q=queue.Queue(maxsize=20000); overflow=threading.Event(); guard=threading.Lock()
broker=Broker(Path(os.getenv('FYERS_CREDENTIALS_DIR',str(ROOT/'.secrets/fyers'))))
master={};master_day=None;authenticated=False;auth_error='Checking FYERS login';auth_at=0
last_stream_spot=0;last_rest_spot=0;fallback_error=None

output_lock=threading.Lock()
def emit(v):
    with output_lock:print('DATA '+json.dumps(v,allow_nan=False,separators=(',',':')),flush=True)
def active():
    n=datetime.now(IST)
    return n.weekday()<5 and n.date().isoformat() not in HOLIDAYS and '09:14:00'<=n.strftime('%H:%M:%S')<'15:31:00'
class Feed(MarketFeed):
    def on_message(self,m):
        global last_stream_spot
        super().on_message(m)
        if not isinstance(m,dict) or not m.get('symbol'):return
        try:
            t=float(m.get('exch_feed_time') or m.get('last_traded_time') or 0)
            p=float(m.get('ltp') or 0)
            if not math.isfinite(p) or not math.isfinite(t) or p<=0 or not 0<=time.time()-t<=3:return
            item={'symbol':m['symbol'],'ltp':p,'at':t}
            for dest,src in [('bid','bid_price'),('ask','ask_price'),('bid_qty','bid_size'),('ask_qty','ask_size')]:
                v=float(m.get(src) or 0);item[dest]=v if math.isfinite(v) else 0
            q.put_nowait(item)
            if item['symbol']=='NSE:NIFTY50-INDEX':last_stream_spot=time.time()
        except queue.Full:overflow.set()
        except (ValueError,TypeError):pass
feed=Feed(broker.credentials,lambda *a:None,active)
feed.subscribe('IDX_I','13',required=True)

def fallback():
    global last_rest_spot,fallback_error
    reader=Broker(Path(os.getenv('FYERS_CREDENTIALS_DIR',str(ROOT/'.secrets/fyers'))))
    while True:
        if active() and authenticated and time.time()-last_stream_spot>1.5:
            started=time.time()
            try:
                result=reader.request('GET','/quotes?symbols=NSE%3ANIFTY50-INDEX',data_api=True)
                received=time.time();item=decode_spot(result,started,received)
                if item and received-last_stream_spot>1.5:
                    q.put_nowait(item);last_rest_spot=received;fallback_error=None
            except Exception:
                fallback_error='FYERS spot snapshot fallback unavailable; retrying'
        time.sleep(1)

def refresh():
    global master,master_day,authenticated,auth_error,auth_at
    next_auth=next_master=0
    while True:
        now=time.time()
        if now>=next_auth:
            next_auth=now+60
            try:
                status=broker.auth.status(verify=True);authenticated=status['valid'];auth_error=status['error'];auth_at=now
            except Exception:authenticated=False;auth_error='FYERS login verification unavailable';auth_at=now
        if authenticated and now>=next_master:
            next_master=now+300
            try:
                day=datetime.now(IST).date().isoformat();records=broker._master('NSE');rows={}
                for symbol,v in records.items():
                    expiry=datetime.fromtimestamp(int(v['expiryDate']),IST).date().isoformat()
                    if v['underSym']=='NIFTY' and expiry>=day:
                        rows[symbol]={'symbol':symbol,'strike':float(v['strikePrice']),'lotSize':int(v['minLotSize']),'expiry':expiry,'type':v['optType']}
                if not rows:raise ValueError('Empty master')
                with guard:master=rows;master_day=day
                emit({'kind':'master','day':day,'contracts':list(rows.values()),'holidays':HOLIDAYS})
            except Exception:
                next_master=now+30;emit({'kind':'error','error':'FYERS instrument master unavailable; retrying'})
        time.sleep(.2)
def controls():
    for line in sys.stdin:
        try:
            data=json.loads(line);symbols=data.get('symbols',[])
            if len(symbols)>100:continue
            with guard:allowed=[s for s in symbols if s in master]
            for symbol in allowed:feed.subscribe('NSE_FNO',symbol)
        except Exception:pass
threading.Thread(target=refresh,daemon=True).start();threading.Thread(target=controls,daemon=True).start();threading.Thread(target=fallback,daemon=True).start();feed.start()
while True:
    ticks=[]
    for _ in range(20000):
        try:ticks.append(q.get_nowait())
        except queue.Empty:break
    lost=overflow.is_set();overflow.clear()
    rest_live=time.time()-last_rest_spot<=3
    emit({'kind':'ticks','broker':'FYERS','ticks':ticks,'lost':lost,'transport':feed.connected or rest_live,'authenticated':bool(authenticated and time.time()-auth_at<90),'error':auth_error or (None if rest_live else feed.last_error or fallback_error),'market_open':active(),'at':time.time()})
    time.sleep(.2)
