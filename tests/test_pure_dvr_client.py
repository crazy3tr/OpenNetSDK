#!/usr/bin/env python3
"""
Unit tests for OpenXM-DVR PureDvrClient using realistic socket mocks.
"""

from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch
import struct
import json
import tempfile
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python")))
from pure_dvr_client import sofia_hash, NetSdkPacket, RecordFile, PureDvrClient

class MockSocket:
    def __init__(self, incoming_bytes: bytes = b""):
        self._in = bytearray(incoming_bytes)
        self.sent = bytearray()
        self.timeout = None

    def settimeout(self, t):
        self.timeout = t

    def connect(self, addr):
        pass

    def sendall(self, data: bytes):
        self.sent.extend(data)

    def recv(self, n: int) -> bytes:
        if not self._in:
            return b""
        chunk = self._in[:n]
        del self._in[:n]
        return bytes(chunk)

    def close(self):
        pass

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

    @patch('socket.socket')
    def test_client_connect(self, mock_sock_cls):
        # Build mock response for TYPE_LOGIN_RESP (status 100 at offset 8)
        login_body = struct.pack('<IIII', 0x12345678, 0, 100, 0)
        login_resp_pkt = NetSdkPacket.pack(NetSdkPacket.TYPE_LOGIN_RESP, login_body, session_id=0x12345678, seq=0)

        mock_sock = MockSocket(login_resp_pkt)
        mock_sock_cls.return_value = mock_sock

        client = PureDvrClient("192.168.1.100", 34567)
        ok = client.connect("admin", "")
        self.assertTrue(ok)
        self.assertEqual(client.session_id, 0x12345678)

    def test_search_files_parsing(self):
        client = PureDvrClient("192.168.1.100", 34567)
        client.session_id = 0x55AA

        # Construct search response payload:
        # header + status(4), pad(12), file_count(4), pad(4), 184-byte record
        rec_st = struct.pack('<6i', 2026, 10, 14, 12, 0, 0)
        rec_et = struct.pack('<6i', 2026, 10, 14, 12, 30, 0)
        path_bytes = b"/idea0/2026-10-14/001/12.00.00-12.30.00[R][0].h264".ljust(108, b'\x00')
        rec_bytes = struct.pack('<II', 0, 15360) + path_bytes + rec_st + rec_et + (b'\x00' * 20)
        self.assertEqual(len(rec_bytes), 184)

        search_body = (
            struct.pack('<IIII', 0, 100, 0, 0) + # status 100
            struct.pack('<iI', 1, 0) +          # file_count = 1
            rec_bytes
        )
        search_pkt = NetSdkPacket.pack(NetSdkPacket.TYPE_SEARCH_RESP, search_body, session_id=0x55AA, seq=1)

        client.ctrl_sock = MockSocket(search_pkt)
        records = client.search_files(channel=0, year=2026, month=10, day=14)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].start_time, "12:00:00")
        self.assertEqual(records[0].end_time, "12:30:00")
        self.assertAlmostEqual(records[0].size_mb, 15.0, places=1)

    def test_get_channel_titles_json_and_utf8(self):
        client = PureDvrClient("192.168.1.100", 34567)
        client.session_id = 0x55AA

        json_data = json.dumps({"Name": "ChannelTitle", "ChannelTitle": ["Giriş Kapısı", "Bahçe"], "Ret": 100}, ensure_ascii=False).encode('utf-8')
        resp_pkt = NetSdkPacket.pack(1043, json_data + b'\n\x00', session_id=0x55AA, seq=12)

        client.ctrl_sock = MockSocket(resp_pkt)
        titles = client.get_channel_titles()

        self.assertEqual(titles, ["Giriş Kapısı", "Bahçe"])

    @patch('socket.socket')
    def test_download_file_size_tolerance(self, mock_sock_cls):
        client = PureDvrClient("192.168.1.100", 34567)
        dl_resp = NetSdkPacket.pack(NetSdkPacket.TYPE_DOWNLOAD_RESP, b"\x00"*16, session_id=0x55AA)
        ka_resp = NetSdkPacket.pack(NetSdkPacket.TYPE_KEEPALIVE_RESP, b"\x00"*16, session_id=0x55AA)
        client.ctrl_sock = MockSocket(dl_resp + (ka_resp * 10))

        # Target size is 100 KB = 102400 bytes
        # Suppose DVR reports 100 KB, but actual payload is 101400 bytes (1000 bytes less due to rounding)
        actual_stream = b"X" * 101400
        data_chunk_pkt = NetSdkPacket.pack(NetSdkPacket.TYPE_DATA_CHUNK, actual_stream, session_id=0x55AA)
        # Add claim and download responses
        claim_resp = NetSdkPacket.pack(NetSdkPacket.TYPE_CLAIM_RESP, b"\x00"*16, session_id=0x55AA)

        data_sock = MockSocket(claim_resp + data_chunk_pkt)
        mock_sock_cls.return_value = data_sock

        rec = RecordFile(channel=0, size_kb=100, remote_path="/idea0/test.h264", st_raw=b"", et_raw=b"")

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            ok = client.download_file(rec, tmp_path)
            # Should succeed because 101400 >= (102400 - 2048 = 100352)
            self.assertTrue(ok)
            self.assertEqual(os.path.getsize(tmp_path), 101400)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch('socket.socket')
    def test_download_file_failure_does_not_call_progress_100(self, mock_sock_cls):
        client = PureDvrClient("192.168.1.100", 34567)
        dl_resp = NetSdkPacket.pack(NetSdkPacket.TYPE_DOWNLOAD_RESP, b"\x00"*16, session_id=0x55AA)
        ka_resp = NetSdkPacket.pack(NetSdkPacket.TYPE_KEEPALIVE_RESP, b"\x00"*16, session_id=0x55AA)
        client.ctrl_sock = MockSocket(dl_resp + (ka_resp * 10))

        # Target size 100 KB, but socket only returns 10 KB then disconnects
        partial_stream = b"X" * 10240
        data_chunk_pkt = NetSdkPacket.pack(NetSdkPacket.TYPE_DATA_CHUNK, partial_stream, session_id=0x55AA)
        claim_resp = NetSdkPacket.pack(NetSdkPacket.TYPE_CLAIM_RESP, b"\x00"*16, session_id=0x55AA)

        data_sock = MockSocket(claim_resp + data_chunk_pkt)
        mock_sock_cls.return_value = data_sock

        rec = RecordFile(channel=0, size_kb=100, remote_path="/idea0/test.h264", st_raw=b"", et_raw=b"")

        progress_calls = []
        def cb(pct, total, speed):
            progress_calls.append(pct)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            ok = client.download_file(rec, tmp_path, progress_callback=cb)
            self.assertFalse(ok)
            self.assertNotIn(100, progress_calls)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_get_channel_titles_1048_json_fallback(self):
        client = PureDvrClient("192.168.1.100", 34567)
        client.session_id = 0x55AA

        # Attempt 1 (1042): returns empty or broken packet
        broken_1042 = NetSdkPacket.pack(1043, b"", session_id=0x55AA, seq=12)

        # Attempt 2 (1048): returns JSON response with ChannelTitle
        json_1048 = json.dumps({"Name": "ChannelTitle", "ChannelTitle": ["Front Door", "Warehouse"], "Ret": 100}).encode('utf-8')
        resp_1048 = NetSdkPacket.pack(1049, json_1048 + b'\n\x00', session_id=0x55AA, seq=13)

        client.ctrl_sock = MockSocket(broken_1042 + resp_1048)
        titles = client.get_channel_titles()

        self.assertEqual(titles, ["Front Door", "Warehouse"])

if __name__ == '__main__':
    unittest.main()
