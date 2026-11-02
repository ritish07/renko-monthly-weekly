import unittest,struct
from dhan_datafeed import decode
class DecodeTests(unittest.TestCase):
 def test_index_without_timestamp(self):
  p=struct.pack('<BHBIf',1,12,0,13,25000)
  q=decode(p,1792650000)
  self.assertEqual(q['symbol'],'NSE:NIFTY50-INDEX');self.assertEqual(q['at'],1792650000);self.assertEqual(q['timestampBasis'],'received')
 def test_depth_and_stale_rejection(self):
  p=bytearray(162);struct.pack_into('<BHBI',p,0,8,162,2,12345);struct.pack_into('<f',p,8,100);struct.pack_into('<I',p,14,1792650000);struct.pack_into('<iihhff',p,62,65,130,1,2,99,101)
  q=decode(p,1792650001);self.assertEqual(q['symbol'],'NSE_FNO:12345');self.assertEqual(q['bid_qty'],65);self.assertEqual(q['ask'],101);self.assertIsNone(decode(p,1792650004))
 def test_invalid_packet(self):
  self.assertIsNone(decode(b'bad',1792650000));self.assertIsNone(decode(struct.pack('<BHBIf',1,12,0,13,float('nan')),1792650000))
if __name__=='__main__':unittest.main()
