#!/usr/bin/env python3
"""
Unit tests for OpenXM-DVR Pure Python Client.
"""

from __future__ import annotations
import unittest
import struct
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from pure_dvr_client import sofia_hash, NetSdkPacket, RecordFile, PureDvrClient

class TestPureDvrClient(unittest.TestCase):
    def test_sofia_hash(self):
        self.assertEqual(sofia_hash(""), "tlJwpbo6")
        self.assertEqual(sofia_hash("admin"), "6QNMIQGe")
        self.assertEqual(sofia_hash("123456"), "nTBCS19C")

    def test_packet_pack_and_unpack(self):
        payload = b"Hello NetSDK"
        pkt = NetSdkPacket.pack(NetSdkPacket.TYPE_KEEPALIVE_REQ, payload, session_id=0x12345678, seq=42)
        self.assertEqual(len(pkt), 20 + len(payload))
        self.assertEqual(pkt[:2], b'\xff\x00')
        
        m, v, sess, seq, f0, f1, ptype, plen = NetSdkPacket.unpack_header(pkt[:20])
        self.assertEqual(m, 0xFF)
        self.assertEqual(v, 0x00)
        self.assertEqual(sess, 0x12345678)
        self.assertEqual(seq, 42)
        self.assertEqual(ptype, NetSdkPacket.TYPE_KEEPALIVE_REQ)
        self.assertEqual(plen, len(payload))

    def test_record_file_path_parsing(self):
        path = "/idea0/2026-10-13/001/14.05.00-14.35.30[H][@1a2b][0].h264"
        rec = RecordFile(channel=0, size_kb=20480, remote_path=path, st_raw=b"", et_raw=b"")
        self.assertEqual(rec.date_str, "2026-10-13")
        self.assertEqual(rec.start_time, "14:05:00")
        self.assertEqual(rec.end_time, "14:35:30")
        self.assertAlmostEqual(rec.size_mb, 20.0, places=1)

    def test_record_file_binary_timestamp_fallback(self):
        st_raw = struct.pack('<6i', 2026, 10, 14, 9, 30, 0)
        et_raw = struct.pack('<6i', 2026, 10, 14, 10, 0, 0)
        path = "/idea0/unconventional_name.h264"
        rec = RecordFile(channel=1, size_kb=10240, remote_path=path, st_raw=st_raw, et_raw=et_raw)
        self.assertEqual(rec.date_str, "2026-10-14")
        self.assertEqual(rec.start_time, "09:30:00")
        self.assertEqual(rec.end_time, "10:00:00")

    def test_utf8_json_serialization(self):
        titles = ["Giriş Kapısı", "Depo", "Bahçe"]
        payload = json.dumps({"Name": "ChannelTitle", "ChannelTitle": titles}, ensure_ascii=False).encode('utf-8')
        self.assertIn("Giriş".encode('utf-8'), payload)
        self.assertNotIn(b'\\u0131', payload)

    def test_search_files_default_date_struct(self):
        now = datetime.now()
        raw_template = bytes.fromhex(
            'c7000000000000000000000000000000683236340000000000000000000000000000000000000000'
            '2a00000000000000000000000000000000000000000000000000000000000000ffff0000'
            'ea0700000a0000000d0000000000000000000000000000000000000000000000'
            'ea0700000a0000000d00000000000000170000003b0000003b00000000000000'
        )
        payload = bytearray(raw_template)
        struct.pack_into('<III', payload, 76, now.year, now.month, now.day)
        y, m, d = struct.unpack_from('<III', payload, 76)
        self.assertEqual((y, m, d), (now.year, now.month, now.day))

if __name__ == '__main__':
    unittest.main()
