"""Dedicated read-only Dhan stream. Never submits broker orders."""
import sys,json,time,threading,queue,math,struct
from pathlib import Path
from urllib.parse import urlencode
from local_broker import DhanAdapter, split_packets, IST, CONFIG
from websockets.sync.client import connect
from datetime import datetime
a=DhanAdapter()
lock=threading.Lock();output=threading.Lock();wanted=set();ticks=queue.Queue(20000)
status={'transport':False,'authenticated':False,'error':'Checking Dhan login'}
master_day=None;auth_at=0;lost=threading.Event()
def emit(v):
 with output:print('DATA '+json.dumps(v,allow_nan=False,separators=(',',':')),flush=True)
def controls():
 global wanted
 for line in sys.stdin:
  try:
   symbols=json.loads(line).get('symbols',[])
   if len(symbols)<=100:
    with lock:wanted={s for s in symbols if s in a.master}
  except Exception:pass
def refresh():
 global master_day,auth_at
 while True:
  try:
   a.broker.profile();status['authenticated']=True;auth_at=time.time();status['error']=None
   a.refresh_master(time.time())
   if a.master_day!=master_day:
    rows=[{'symbol':c['symbol'],'strike':c['strike'],'lotSize':c['lot_size'],'expiry':c['expiry'],'type':c['side']} for c in a.master.values() if c['asset']=='NIFTY' and c['segment']=='NSE_FNO']
    if not rows:raise ValueError('Empty Nifty master')
    emit({'kind':'master','day':a.master_day,'contracts':rows,'holidays':CONFIG['holidays']});master_day=a.master_day
  except Exception as e:
   status['authenticated']=False;status['error']='Dhan authentication or instrument master unavailable ('+type(e).__name__+')'
  time.sleep(60)
def decode(packet,received):
 if len(packet)<12:return None
 code,length,seg,sid=struct.unpack_from('<BHBI',packet)
 if length!=len(packet):return None
 if seg==0 and sid==13 and code in (1,2,4,8):
  price=struct.unpack_from('<f',packet,8)[0]
  # Index packets have no exchange timestamp: use observed stream receipt time.
  stamp=received if code==1 else struct.unpack_from('<I',packet,12 if code==2 else 14)[0]
  symbol='NSE:NIFTY50-INDEX';basis='received' if code==1 else 'exchange'
 elif seg==2 and code==8 and len(packet)>=162:
  price=struct.unpack_from('<f',packet,8)[0];stamp=struct.unpack_from('<I',packet,14)[0];symbol='NSE_FNO:'+str(sid);basis='exchange'
 else:return None
 if abs(received-(stamp-19800))<=3:stamp-=19800
 if not math.isfinite(price) or price<=0 or not 0<=received-stamp<=3:return None
 item={'symbol':symbol,'ltp':price,'at':stamp,'timestampBasis':basis}
 if seg==2:
  bq,aq,_,_,bid,ask=struct.unpack_from('<iihhff',packet,62)
  if not all(math.isfinite(v) for v in [bid,ask]):return None
  item.update(bid=bid,ask=ask,bid_qty=bq,ask_qty=aq)
 return item
def stream():
 while True:
  if not a.active() or not status['authenticated']:time.sleep(1);continue
  try:
   creds=a.broker.credentials();client,token=creds
   url='wss://api-feed.dhan.co?'+urlencode({'version':2,'token':token,'clientId':client,'authType':2})
   with connect(url,open_timeout=10,ping_interval=20,ping_timeout=10) as ws:
    status['transport']=True;sent=set();last_spot=time.monotonic()
    while a.active() and a.broker.credentials()==creds and status['authenticated']:
     with lock:desired={('IDX_I','13')}|{('NSE_FNO',s.split(':')[1]) for s in wanted}
     for code,items in [(22,sent-desired),(21,desired-sent)]:
      if items:ws.send(json.dumps({'RequestCode':code,'InstrumentCount':len(items),'InstrumentList':[{'ExchangeSegment':seg,'SecurityId':sid} for seg,sid in sorted(items)]}))
     sent=desired
     if time.monotonic()-last_spot>20:raise TimeoutError('Missing Nifty spot')
     try:message=ws.recv(timeout=.5)
     except TimeoutError:continue
     for packet in split_packets(message):
      if packet[0]==50:raise ConnectionError('Broker disconnected')
      item=decode(packet,time.time())
      if item and (item['symbol']=='NSE:NIFTY50-INDEX' or ('NSE_FNO',item['symbol'].split(':')[1]) in desired):
       if item['symbol']=='NSE:NIFTY50-INDEX':last_spot=time.monotonic()
       try:ticks.put_nowait(item)
       except queue.Full:lost.set()
  except Exception as e:status['error']='Dhan stream reconnecting ('+type(e).__name__+')'
  finally:status['transport']=False
  time.sleep(3)
if __name__=='__main__':
 for target in [controls,refresh,stream]:threading.Thread(target=target,daemon=True).start()
 while True:
  batch=[]
  for _ in range(20000):
   try:batch.append(ticks.get_nowait())
   except queue.Empty:break
  dropped=lost.is_set();lost.clear()
  emit({'kind':'ticks','broker':'DHAN','ticks':batch,'lost':dropped,'transport':status['transport'],'authenticated':status['authenticated'] and time.time()-auth_at<90,'error':status['error'],'market_open':a.active(),'at':time.time()})
  time.sleep(.2)
