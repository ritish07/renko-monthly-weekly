"""Standalone Dhan market-data adapter. No broker order endpoints or methods."""
import csv
import io
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST=timezone(timedelta(hours=5,minutes=30))
ROOT=Path(__file__).parent
CONFIG=json.loads((ROOT/'config.json').read_text())


def split_packets(message):
    import struct
    if not isinstance(message,bytes):return []
    result=[];offset=0
    while offset<len(message):
        if offset+8>len(message):return []
        size=struct.unpack_from('<H',message,offset+1)[0]
        if size<8 or offset+size>len(message):return []
        result.append(message[offset:offset+size]);offset+=size
    return result


class DhanData:
    def credentials(self):
        client=os.getenv('DHAN_CLIENT_ID','');token=os.getenv('DHAN_ACCESS_TOKEN','')
        path=os.getenv('DHAN_CREDENTIALS_FILE')
        if path:
            saved=json.loads(Path(path).expanduser().read_text())
            client=saved.get('client_id') or client;token=saved.get('access_token') or token
        return str(client),str(token)

    def profile(self):
        client,token=self.credentials()
        if not client or not token:raise ValueError('Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN')
        req=urllib.request.Request('https://api.dhan.co/v2/profile',headers={'access-token':token,'client-id':client})
        with urllib.request.urlopen(req,timeout=15) as r:profile=json.load(r)
        if str(profile.get('dhanClientId'))!=client:raise ValueError('Dhan profile does not match configured client ID')
        return profile


class DhanAdapter:
    def __init__(self):
        self.broker=DhanData();self.master={};self.master_day=None

    def active(self):
        now=datetime.now(IST)
        return now.weekday()<5 and now.date().isoformat() not in CONFIG['holidays'] and '09:14:00'<=now.strftime('%H:%M:%S')<'15:31:00'

    def refresh_master(self,now):
        date=datetime.fromtimestamp(now,IST).date().isoformat()
        if self.master_day==date:return
        with urllib.request.urlopen('https://images.dhan.co/api-data/api-scrip-master-detailed.csv',timeout=35) as r:
            rows=csv.DictReader(io.StringIO(r.read().decode()))
            master={}
            for row in rows:
                if row.get('UNDERLYING_SYMBOL')!='NIFTY' or row.get('INSTRUMENT')!='OPTIDX' or row.get('EXCH_ID')!='NSE' or row.get('OPTION_TYPE') not in ('CE','PE'):continue
                expiry=row.get('SM_EXPIRY_DATE','')[:10]
                if expiry<date:continue
                sid=str(int(float(row['SECURITY_ID'])));symbol='NSE_FNO:'+sid
                lot=int(float(row['LOT_SIZE']));strike=float(row['STRIKE_PRICE'])
                if lot<=0 or strike<=0:continue
                master[symbol]={'symbol':symbol,'strike':strike,'lot_size':lot,'expiry':expiry,
                                'side':row['OPTION_TYPE'],'asset':'NIFTY','segment':'NSE_FNO'}
        if not master:raise ValueError('Dhan returned no current NIFTY option contracts')
        self.master=master;self.master_day=date
