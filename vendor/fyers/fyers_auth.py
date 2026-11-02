from __future__ import annotations
import base64, hashlib, json, os, secrets, tempfile, threading, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request
from transport import urlopen_ipv4 as urlopen
from urllib.error import HTTPError
from datetime import datetime
from strategy import IST
BASE='https://api-t1.fyers.in'

class FyersAuth:
    def __init__(self,data_dir):
        self.path=Path(data_dir)/'credentials.json';self.lock=threading.RLock();self.last_verified=None;self.states={}
    def saved(self):
        with self.lock:
            return json.loads(self.path.read_text()) if self.path.exists() else {}
    def credentials(self):
        d=self.saved();return d.get('app_id',''),d.get('access_token','')
    def secret(self):return self.saved().get('secret','')
    def expiry(self,token):
        try:return float(json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))['exp'])
        except (ValueError,KeyError,IndexError,TypeError):return 0
    def token(self):
        token=self.credentials()[1]
        return token if token and self.expiry(token)>time.time()+30 else None
    def profile(self,app_id=None,token=None):
        if app_id is None:app_id,token=self.credentials()
        if not app_id or not token:raise ValueError('Fyers App ID and daily access token are required')
        req=Request(BASE+'/api/v3/profile',headers={'Authorization':app_id+':'+token,'Accept':'application/json'})
        try:
            with urlopen(req,timeout=15) as r:result=json.load(r)
        except HTTPError as e:raise RuntimeError('Fyers token verification failed (HTTP '+str(e.code)+')') from None
        if result.get('s')!='ok' or not (result.get('data') or {}).get('fy_id'):raise RuntimeError('Fyers rejected the access token')
        self.last_verified=datetime.now(IST).isoformat()
        return str(result['data']['fy_id'])
    def write(self,d):
        fd,path=tempfile.mkstemp(prefix='.credentials-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as f:json.dump(d,f);f.flush();os.fsync(f.fileno())
            os.replace(path,self.path)
        finally:
            if os.path.exists(path):os.unlink(path)
    def save(self,app_id,token,secret='',redirect_uri=''):
        if not isinstance(app_id,str) or not isinstance(token,str):raise ValueError('Invalid credentials')
        app_id=app_id.strip();token=token.strip()
        if not app_id or len(app_id)>80 or ':' in app_id or any(c.isspace() for c in app_id):raise ValueError('Enter the trading App ID')
        if token.startswith(app_id+':'):token=token[len(app_id)+1:]
        if not token or len(token)>8192 or any(c.isspace() for c in token):raise ValueError('Enter the daily access token')
        if self.expiry(token)<=time.time()+30:raise ValueError('Token is expired or has no expiry')
        with self.lock:
            old=self.saved();account=self.profile(app_id,token)
            if old.get('account') and old['account']!=account:raise ValueError('Token belongs to a different Fyers account')
            if old.get('app_id') and old['app_id']!=app_id:raise ValueError('App ID cannot change after the first verified connection')
            self.write({'app_id':app_id,'access_token':token,'account':account,'secret':secret or old.get('secret',''),'redirect_uri':redirect_uri or old.get('redirect_uri',''),'saved_at':datetime.now(IST).isoformat()})
        return self.status(verify=True)
    def status(self,verify=False):
        d=self.saved();token=d.get('access_token','');exp=self.expiry(token);error=None;valid=False
        if token and exp>time.time()+30:
            try:
                if verify:self.profile()
                valid=True
            except Exception as e:error=str(e)
        elif token:error='Daily access token expired. Complete Fyers 2FA and save a new token.'
        return {'valid':valid,'state':'valid' if valid else 'expired' if token and exp<=time.time()+30 else 'invalid' if token else 'missing','app_id':d.get('app_id',''),'account':d.get('account'),'valid_until':datetime.fromtimestamp(exp,IST).isoformat() if exp else None,'last_verified':self.last_verified,'error':error,'login_available':bool(d.get('secret') and d.get('redirect_uri')),'daily_2fa_required':True}
    def login_url(self):
        d=self.saved()
        if not d.get('secret') or not d.get('redirect_uri'):raise ValueError('Save app secret and registered redirect URL first')
        state=secrets.token_urlsafe(32);self.states={state:time.time()+600}
        return BASE+'/api/v3/generate-authcode?'+urlencode({'client_id':d['app_id'],'redirect_uri':d['redirect_uri'],'response_type':'code','state':state})
    def exchange(self,code,state):
        if self.states.pop(state,0)<time.time():raise ValueError('Login session expired; start Login with Fyers again')
        d=self.saved();digest=hashlib.sha256((d['app_id']+':'+d['secret']).encode()).hexdigest()
        req=Request(BASE+'/api/v3/validate-authcode',data=json.dumps({'grant_type':'authorization_code','appIdHash':digest,'code':code}).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=15) as r:result=json.load(r)
        except HTTPError as e:
            try:failure=json.loads(e.read(4096))
            except (ValueError,TypeError):failure={}
            code=failure.get('code')
            hint=' Start Login with Fyers again for a fresh code.' if code in (-437,-436) else ' Check the app credentials in FYERS if this persists.'
            raise RuntimeError('Fyers login exchange rejected (HTTP '+str(e.code)+', broker code '+str(code or 'unavailable')+').'+hint) from None
        if result.get('s')!='ok' or not result.get('access_token'):raise RuntimeError('Fyers rejected the authorization code')
        return self.save(d['app_id'],result['access_token'])
