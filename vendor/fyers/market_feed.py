"""FYERS SDK stream; stale/disconnected quotes never trigger orders."""
import logging, math, os, threading, time
from broker import INDEX
from datetime import datetime
from strategy import IST
class MarketFeed:
    def __init__(self,credentials,on_quote,active=lambda:True):
        self.credentials=credentials;self.on_quote=on_quote;self.active=active;self.subscriptions=set();self.quotes={};self.connected=False;self.lock=threading.RLock();self.thread=None;self.socket=None;self.stop_event=threading.Event();self.last_message=0.;self.last_error=None;self.session_day=datetime.now(IST).date();self.rejected_symbols=set();self.required={};self.requested={};self.generation=0;self.sent=set();self.connected_at=0.;self.repair_at=0.;self.repair_attempts=0;self.reconnect_count=0
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self.run,daemon=True,name='fyers-market-feed');self.thread.start()
    def subscribe(self,segment,security_id,required=False):
        with self.lock:
            self.roll_session()
            if INDEX.get(str(security_id),str(security_id)) not in self.rejected_symbols:
                key=(segment,str(security_id));self.subscriptions.add(key)
                self.requested[key]=time.monotonic()
                if required:self.required[key]=time.monotonic()
    def health(self):
        with self.lock:
            now=time.monotonic();rows={}
            for key,required_at in self.required.items():
                if key[1] not in INDEX and now-required_at>45:continue
                item=self.quotes.get(key)
                age=max(now-item[1],abs(time.time()-item[2])) if item else None
                rows[INDEX.get(key[1],key[1])]={'age_seconds':round(age,2) if age is not None else None,
                    'fresh':bool(self.connected and age is not None and age<=5)}
            return {'ready':bool(self.connected and rows and all(r['fresh'] for r in rows.values())),
                    'transport_connected':self.connected,'symbols':rows,'last_error':self.last_error,
                    'reconnects':self.reconnect_count,'repair_attempts':self.repair_attempts}
    def maintain(self):
        # Only this supervisor sends SDK subscription mutations. A successful
        # subscribe call is an intent; fresh per-symbol ticks prove delivery.
        now=time.monotonic()
        with self.lock:
            self.roll_session()
            self.subscriptions={key for key in self.subscriptions if key[1] in INDEX or
                now-self.requested.get(key,now)<=180 or now-self.required.get(key,-1000)<=45}
            desired={INDEX.get(sid,sid) for _,sid in self.subscriptions}
        if not self.connected:return
        removed=self.sent-desired
        if removed:
            self.socket.unsubscribe(symbols=sorted(removed),data_type='SymbolUpdate');self.sent-=removed
        added=desired-self.sent
        if added:
            self.socket.subscribe(symbols=sorted(added),data_type='SymbolUpdate')
            with self.lock:self.sent.update(added-self.rejected_symbols)
        health=self.health()
        missing=sorted(symbol for symbol,row in health['symbols'].items() if not row['fresh'])
        if not missing:
            self.repair_attempts=0;self.repair_at=0.
            if self.last_error and self.last_error.startswith('Recovering missing Fyers quotes:'):self.last_error=None
            return
        if now-self.connected_at<10:return
        if self.repair_attempts and now-self.repair_at<10:return
        if self.repair_attempts>=2:
            self.last_error='Required Fyers quotes missing; reconnecting'
            logging.error('Fyers feed watchdog reconnect: missing=%s',','.join(missing))
            self.disconnect();return
        self.repair_attempts+=1;self.repair_at=now
        self.last_error='Recovering missing Fyers quotes: '+', '.join(missing)
        logging.warning('Fyers feed subscription repair %s: missing=%s',self.repair_attempts,','.join(missing))
        # Replay the complete desired set, so recovery cannot silently omit an
        # older option while newly added options continue receiving data.
        self.socket.subscribe(symbols=sorted(desired),data_type='SymbolUpdate')
    def quote(self,segment,security_id,max_age=3):
        with self.lock:item=self.quotes.get((segment,str(security_id))) if self.connected else None
        if item and time.monotonic()-item[1]<=max_age and abs(time.time()-item[2])<=5:return item[0],item[2]
        return None
    def disconnect(self,*args):
        with self.lock:self.connected=False;self.quotes.clear()
    def roll_session(self):
        # Caller holds lock. Only index subscriptions survive overnight.
        day=datetime.now(IST).date()
        if day!=self.session_day:
            self.subscriptions={key for key in self.subscriptions if key[1] in INDEX}
            self.quotes.clear();self.rejected_symbols.clear();self.required={key:at for key,at in self.required.items() if key[1] in INDEX};self.session_day=day
    def on_error(self,message=None,*args):
        if isinstance(message,dict) and message.get('type')=='sub':
            invalid=message.get('invalid_symbols')
            if isinstance(invalid,list) and invalid and all(isinstance(s,str) for s in invalid):
                with self.lock:
                    self.rejected_symbols.update(invalid)
                    self.subscriptions={key for key in self.subscriptions if INDEX.get(key[1],key[1]) not in self.rejected_symbols}
                    self.quotes={key:value for key,value in self.quotes.items() if key in self.subscriptions}
                self.last_error='Rejected invalid Fyers subscription symbols'
                return
        self.last_error='Fyers feed error; reconnecting';self.disconnect()
    def on_message(self,message):
        if not isinstance(message,dict):return
        symbol=message.get('symbol')
        try:
            price=float(message.get('ltp') or 0);stamp=float(message.get('exch_feed_time') or message.get('last_traded_time') or 0)
        except (ValueError,TypeError):return
        if not symbol or not math.isfinite(price) or price<=0 or abs(time.time()-stamp)>5:return
        self.last_message=time.monotonic()
        with self.lock:
            matches=[k for k in self.subscriptions if INDEX.get(k[1],k[1])==symbol]
            for key in matches:self.quotes[key]=(price,time.monotonic(),stamp)
        for segment,sid in matches:self.on_quote(segment,sid,price,stamp)
    def run(self):
        from fyers_apiv3.FyersWebsocket.data_ws import FyersDataSocket
        while not self.stop_event.is_set():
            if not self.active() or not all(self.credentials()):self.stop_event.wait(2);continue
            app,token=self.credentials();self.generation+=1;generation=self.generation;self.sent=set()
            self.reconnect_count+=1
            def opened(expected=generation):
                if expected!=self.generation:return
                with self.lock:
                    self.connected=True;self.quotes.clear();self.connected_at=time.monotonic()
                    self.sent.clear();self.last_error=None;self.repair_attempts=0;self.repair_at=0.
            def message(data,expected=generation):
                if expected==self.generation:self.on_message(data)
            def error(*args,expected=generation):
                if expected==self.generation:self.on_error(*args)
            def closed(*args,expected=generation):
                if expected==self.generation:self.disconnect(*args)
            try:
                self.socket=FyersDataSocket(access_token=app+':'+token,write_to_file=False,log_path=os.getenv('DATA_DIR','.'),litemode=False,reconnect=False,on_connect=opened,on_close=closed,on_error=error,on_message=message)
                self.socket.connect()
                deadline=time.monotonic()+20
                while not self.stop_event.is_set() and self.active() and self.credentials()==(app,token):
                    if not self.connected and (self.connected_at or time.monotonic()>deadline):break
                    self.maintain()
                    self.stop_event.wait(.5)
            except Exception:
                self.last_error='Fyers feed unavailable'
                logging.exception('Fyers feed supervisor failed')
            finally:
                self.generation+=1
                self.disconnect()
                self.connected_at=0.
                if self.socket:
                    try:self.socket.close_connection()
                    except Exception:pass
            self.stop_event.wait(3)
