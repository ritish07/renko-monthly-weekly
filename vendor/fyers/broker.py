from __future__ import annotations
import json, math, threading, time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request
from transport import urlopen_ipv4 as urlopen
from urllib.error import HTTPError
from fyers_auth import FyersAuth, BASE
from strategy import IST
from data_budget import DataBudget

INDEX={'13':'NSE:NIFTY50-INDEX','25':'NSE:NIFTYBANK-INDEX','51':'BSE:SENSEX-INDEX'}
ASSET={'13':'NIFTY','25':'BANKNIFTY','51':'SENSEX'}
STATES={1:'CANCELLED',2:'TRADED',3:'ATTENTION',4:'TRANSIT',5:'REJECTED',6:'PENDING',7:'EXPIRED'}
class Broker:
    name='LIVE FYERS';requires_linked_exits=False
    position_linked_exits=True
    def __init__(self,data_dir):
        self.data_budget=DataBudget(data_dir);self.auth=FyersAuth(data_dir);self.master={};self.master_day='';self.lock=threading.RLock();self.request_lock=threading.Lock();self.last_order=0.;self.history_cache={};self.history_lock=threading.RLock();self.last_data_request=0.;self.data_backoff_until=0.
    def credentials(self):return self.auth.credentials()
    def configured(self):return bool(self.auth.token())
    def request(self,method,path,body=None,data_api=False):
        if data_api:
            if method!='GET':raise ValueError('Data API must be read-only')
            return self.data_budget.run(path,lambda:self._request(method,path,body,True))
        return self._request(method,path,body,False)
    def _request(self,method,path,body=None,data_api=False):
        app,token=self.credentials()
        if not self.auth.token():raise RuntimeError('Fyers daily login required')
        base='https://api-t1.fyers.in/data' if data_api else BASE+'/api/v3'
        req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':app+':'+token,'Content-Type':'application/json','Accept':'application/json'})
        # Never retry a mutation: an acknowledgement can be lost after acceptance.
        with self.request_lock:
            if method!='GET':
                delay=.15-(time.monotonic()-self.last_order)
                if delay>0:time.sleep(delay)
                self.last_order=time.monotonic()
            try:
                with urlopen(req,timeout=15) as r:result=json.load(r)
            except HTTPError as e:
                detail=''
                if data_api and e.code==429:
                    try:
                        payload=json.loads(e.read(4096))
                        detail=': '+str(payload.get('message',''))[:200]
                    except (ValueError,AttributeError,TypeError):pass
                error=RuntimeError('Fyers '+method+' '+path.split('?')[0]+' HTTP '+str(e.code)+detail)
                if data_api and e.code==429:
                    try:error.retry_at=time.time()+max(65,float(e.headers.get('Retry-After','65')))
                    except (ValueError,TypeError,AttributeError):error.retry_at=time.time()+65
                raise error from None
        if not isinstance(result,dict) or result.get('s')!='ok':raise RuntimeError('Fyers request rejected (code '+str(result.get('code'))+')')
        return result
    def _master(self,exchange):
        day=datetime.now(IST).date().isoformat()
        with self.lock:
            if self.master_day!=day:self.master={};self.master_day=day
            if exchange not in self.master:
                seg='BSE_FO' if exchange=='BSE' else 'NSE_FO'
                with urlopen('https://public.fyers.in/sym_details/'+seg+'_sym_master.json',timeout=30) as r:records=json.load(r)
                if not isinstance(records,dict) or not records:raise RuntimeError('Fyers symbol master unavailable')
                self.master[exchange]={s:v for s,v in records.items() if v.get('underSym') in ('NIFTY','BANKNIFTY','SENSEX') and int(v.get('exInstType') or 0)==14 and v.get('optType') in ('CE','PE') and int(v.get('tradeStatus') or 0)==1}
            return self.master[exchange]
    def lot_sizes(self):return {s:int(v['minLotSize']) for exchange in ('NSE','BSE') for s,v in self._master(exchange).items()}
    def expiry(self,spec):
        asset=ASSET[str(spec['security_id'])];exchange='BSE' if asset=='SENSEX' else 'NSE';today=datetime.now(IST).date().isoformat()
        dates=sorted({datetime.fromtimestamp(int(v['expiryDate']),IST).date().isoformat() for v in self._master(exchange).values() if v['underSym']==asset})
        return next((d for d in dates if d>=today),None) or self._fail('No active Fyers expiry')
    def _fail(self,message):raise RuntimeError(message)
    def chain(self,spec,expiry):
        asset=ASSET[str(spec['security_id'])];oc={}
        for symbol,v in self._master('BSE' if asset=='SENSEX' else 'NSE').items():
            if v['underSym']==asset and datetime.fromtimestamp(int(v['expiryDate']),IST).date().isoformat()==expiry:
                oc.setdefault(f"{float(v['strikePrice']):.6f}",{})[v['optType'].lower()]={'security_id':symbol}
        return {'oc':oc}
    def prepare_contract(self,asset,expiry,strike,side,security_id,lot,require_fresh=True):
        rec=self._master('BSE' if asset=='SENSEX' else 'NSE').get(security_id)
        if not rec or rec['underSym']!=asset or rec['optType']!=side or float(rec['strikePrice'])!=float(strike) or int(rec['minLotSize'])!=int(lot) or datetime.fromtimestamp(int(rec['expiryDate']),IST).date().isoformat()!=expiry:raise RuntimeError('Fyers contract validation failed')
        # Master is fetched anew each session; vendor lastUpdate can be prior trading day.
        return security_id
    def sync_active(self,rows):
        for row in rows:self.prepare_contract(row['asset'],row['expiry'],row['strike'],row['side'],row['security_id'],row['lot_size'],False)
    def candles(self,security_id,segment,instrument='OPTIDX',day=None):
        with self.history_lock:
            day=day or datetime.now(IST).date().isoformat();symbol=INDEX.get(str(security_id),str(security_id));key=(symbol,day,int(time.time())//60)
            if key in self.history_cache:return self.history_cache[key]
            q=urlencode({'symbol':symbol,'resolution':'1','date_format':'1','range_from':day,'range_to':day,'cont_flag':'1'})
            result=self.request('GET','/history?'+q,data_api=True)
            bars=[dict(zip(('timestamp','open','high','low','close','volume'),bar[:6])) for bar in result.get('candles',[])]
            self.history_cache={k:v for k,v in self.history_cache.items() if k[2]==key[2]};self.history_cache[key]=bars
            return bars
    def ltp(self,instruments):
        symbols=[INDEX.get(str(sid),str(sid)) for _,sid in instruments]
        result=self.request('GET','/quotes?'+urlencode({'symbols':','.join(symbols)}),data_api=True)
        values={v['n']:float(v['v']['lp']) for v in result.get('d',[]) if v.get('s')=='ok'}
        return {(seg,str(sid)):values[INDEX.get(str(sid),str(sid))] for seg,sid in instruments if INDEX.get(str(sid),str(sid)) in values}
    def funds(self):
        limits={int(v['id']):float(v.get('equityAmount') or 0) for v in self.request('GET','/funds').get('fund_limit',[])}
        if 10 not in limits:raise RuntimeError('Fyers available balance missing')
        return {'availabelBalance':limits[10],'withdrawableBalance':limits.get(3),'utilizedAmount':limits.get(2)}
    def positions(self):
        return [{'securityId':v['symbol'],'exchangeSegment':'BSE_FNO' if v['symbol'].startswith('BSE:') else 'NSE_FNO','productType':v['productType'],'netQty':int(v['netQty']),'tradingSymbol':v['symbol'],'positionId':v.get('id'),'stopLoss':v.get('stopLoss'),'takeProfit':v.get('takeProfit'),'legType':v.get('legType')} for v in self.request('GET','/positions').get('netPositions',[])]
    def normalize_order(self,v):
        state=int(v['status'])
        if state not in STATES:raise RuntimeError('Unknown Fyers order status')
        symbol=v['symbol']
        return {'orderId':str(v['id']),'correlationId':str(v.get('orderTag') or '').split(':')[-1],'orderStatus':STATES[state],'filledQty':int(v.get('filledQty') or 0),'averageTradedPrice':float(v.get('tradedPrice') or v.get('avgTradePrice') or 0),'securityId':symbol,'exchangeSegment':'BSE_FNO' if symbol.startswith('BSE:') else 'NSE_FNO','transactionType':'BUY' if int(v['side'])==1 else 'SELL','quantity':int(v['qty']),'productType':v.get('productType'),'omsErrorDescription':v.get('message'),'stopPrice':v.get('stopPrice'),'type':v.get('type')}
    def orders(self):
        rows=[]
        for v in self.request('GET','/orders').get('orderBook',[]):
            row=self.normalize_order(v)
            row.update(parentId=str(v.get('parentId') or ''),stopLoss=v.get('stopLoss'),takeProfit=v.get('takeProfit'),legType=v.get('legType'),limitPrice=v.get('limitPrice'))
            rows.append(row)
        return rows
    def attach_exits(self,security_id,quantity,entry_price,stop,target):
        # FYERS TP/SL parameters are OFFSETS from average entry, not prices.
        rec=self._master('BSE' if security_id.startswith('BSE:') else 'NSE').get(security_id)
        if not rec or quantity<=0 or quantity%int(rec['minLotSize']):raise ValueError('Invalid linked-exit lot quantity')
        tick=float(rec['tickSize'])
        sl=round(round((entry_price-stop)/tick)*tick,2)
        tp=round(round((target-entry_price)/tick)*tick,2)
        if not all(math.isfinite(v) and v>0 for v in (sl,tp)):raise ValueError('Linked exits must bracket the confirmed fill price')
        return self.request('PATCH','/positions',{'positionId':security_id+'-INTRADAY','qty':int(quantity),'stopLoss':sl,'takeProfit':tp,'legType':1})
    def cancel_exits(self,security_id):
        return self.request('PATCH','/positions',{'positionId':security_id+'-INTRADAY','stopLoss':None,'takeProfit':None})
    def order(self,order_id):
        rows=[o for o in self.orders() if o['orderId']==str(order_id)]
        if len(rows)!=1:raise RuntimeError('Fyers order lookup ambiguous or missing')
        return rows[0]
    def _payload(self,side,symbol,qty,correlation,typ=2,trigger=0):
        rec=self._master('BSE' if symbol.startswith('BSE:') else 'NSE').get(symbol)
        if not rec or qty<=0 or qty%int(rec['minLotSize']):raise ValueError('Invalid Fyers symbol or lot quantity')
        if int(qty)>int(rec['qtyFreeze']):raise ValueError('Quantity exceeds Fyers freeze limit')
        if datetime.fromtimestamp(int(rec['expiryDate']),IST).date()<datetime.now(IST).date():raise ValueError('Expired Fyers contract')
        tick=float(rec['tickSize']);trigger=round(math.ceil(trigger/tick-1e-9)*tick,2) if trigger else 0
        limit=round(max(tick,math.floor((trigger-max(tick,trigger*.02))/tick)*tick),2) if trigger else 0
        return {'symbol':symbol,'qty':int(qty),'type':typ,'side':1 if side=='BUY' else -1,'productType':'INTRADAY','limitPrice':limit,'stopPrice':trigger,'validity':'DAY','disclosedQty':0,'offlineOrder':False,'stopLoss':0,'takeProfit':0,'orderTag':correlation}
    def place(self,side,segment,security_id,quantity,correlation):
        result=self.request('POST','/orders/sync',self._payload(side,security_id,quantity,correlation));return {'orderId':result.get('id'),'orderStatus':'PENDING'}
    def place_stop(self,segment,security_id,quantity,trigger,correlation):
        quote=self.ltp([(segment,security_id)]).get((segment,security_id))
        if not quote or trigger>=quote:raise RuntimeError('Protective trigger must be below current Fyers option price')
        result=self.request('POST','/orders/sync',self._payload('SELL',security_id,quantity,correlation,4,trigger));return {'orderId':result.get('id'),'orderStatus':'PENDING'}
    def cancel(self,order_id):return self.request('DELETE','/orders/sync',{'id':str(order_id)})
    def modify_stop(self,order_id,security_id,quantity,trigger):
        p=self._payload('SELL',security_id,quantity,'modify',4,trigger)
        return self.request('PATCH','/orders/sync',{'id':str(order_id),'type':4,'qty':int(quantity),'stopPrice':p['stopPrice'],'limitPrice':p['limitPrice']})
