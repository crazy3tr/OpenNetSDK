#!/usr/bin/env python3
"""
OpenXM-DVR - Pure Python Client (Zero Dependencies, Zero DLLs)
Works across Linux, macOS, Windows, Android (Termux/Kivy), Raspberry Pi.
"""

import socket
import struct
import hashlib
import json
import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sofia_hash(password: str) -> str:
    """Computes Xiongmai/Sofia password hash for port 34567."""
    md5 = hashlib.md5(password.encode('utf-8')).digest()
    base62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(base62[(md5[2*i] + md5[2*i+1]) % 62] for i in range(8))

class NetSdkPacket:
    MAGIC_REQ = 0xFF00
    MAGIC_RESP = 0xFF01
    
    TYPE_LOGIN_REQ = 1000
    TYPE_LOGIN_RESP = 1001
    TYPE_SEARCH_REQ = 1440
    TYPE_SEARCH_RESP = 1441
    TYPE_CLAIM_REQ = 1424
    TYPE_CLAIM_RESP = 1425
    TYPE_DOWNLOAD_REQ = 1420
    TYPE_DOWNLOAD_RESP = 1421
    TYPE_DATA_CHUNK = 1426

    @staticmethod
    def pack(pkt_type: int, payload: bytes, session_id: int = 0, seq: int = 0) -> bytes:
        header = struct.pack('<BBxxIIBBHI', 0xFF, 0x00, session_id, seq, 0, 0, pkt_type, len(payload))
        return header + payload

    @staticmethod
    def unpack_header(data: bytes):
        return struct.unpack('<BBxxIIBBHI', data[:20])

class RecordFile:
    def __init__(self, channel: int, size_kb: int, remote_path: str, st_raw: bytes, et_raw: bytes):
        self.channel = channel
        self.size_kb = size_kb
        self.size_mb = size_kb / 1024.0
        self.remote_path = remote_path
        self.st_raw = st_raw
        self.et_raw = et_raw
        
    def __repr__(self):
        return f"<RecordFile ch={self.channel} size={self.size_mb:.1f}MB path={self.remote_path}>"

class PureDvrClient:
    def __init__(self, host: str, port: int = 34567):
        self.host = host
        self.port = port
        self.session_id = 0
        self.ctrl_sock = None

    def connect(self, username: str = "admin", password: str = "") -> bool:
        """Connects and authenticates with the DVR."""
        self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ctrl_sock.settimeout(10.0)
        self.ctrl_sock.connect((self.host, self.port))
        
        # Build Login Payload
        hashed = sofia_hash(password)
        u_bytes = username.encode('ascii').ljust(32, b'\x00')
        p_bytes = hashed.encode('ascii').ljust(32, b'\x00')
        payload = u_bytes + p_bytes + struct.pack('<II', 1, 2)
        
        self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_LOGIN_REQ, payload))
        
        hdr = self._recv_exact(self.ctrl_sock, 20)
        m, v, sess, seq, f0, f1, ptype, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        
        status = struct.unpack('<I', resp[8:12])[0]
        if status == 100:
            self.session_id = sess
            return True
        return False

    def search_files(self, channel: int = 0, year: int = 2026, month: int = 10, day: int = 13) -> list:
        """Queries recording records for a specific day."""
        raw_template = bytes.fromhex(
            'c7000000000000000000000000000000683236340000000000000000000000000000000000000000'
            '2a00000000000000000000000000000000000000000000000000000000000000ffff0000'
            'ea0700000a0000000d0000000000000000000000000000000000000000000000'
            'ea0700000a0000000d00000000000000170000003b0000003b00000000000000'
        )
        payload = bytearray(raw_template)
        struct.pack_into('<I', payload, 0, self.session_id)
        struct.pack_into('<I', payload, 4, channel)
        # Patch date
        struct.pack_into('<III', payload, 76, year, month, day)
        struct.pack_into('<III', payload, 108, year, month, day)
        
        self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_SEARCH_REQ, bytes(payload), self.session_id, 1))
        
        hdr = self._recv_exact(self.ctrl_sock, 20)
        m, v, s, seq, f0, f1, ptype, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        
        file_count = struct.unpack('<i', resp[16:20])[0]
        records = []
        if file_count > 0:
            for i in range(file_count):
                rec = resp[24 + i*184 : 24 + (i+1)*184]
                ch = struct.unpack('<I', rec[0:4])[0]
                sz_kb = struct.unpack('<I', rec[4:8])[0]
                path = rec[8:116].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                records.append(RecordFile(ch, sz_kb, path, rec[116:140], rec[140:164]))
        return records

    def download_file(self, record: RecordFile, destination_path: str, progress_callback=None, max_bytes=None) -> bool:
        """Downloads a file directly from DVR hard drive via secondary Data Socket."""
        data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_sock.settimeout(10.0)
        data_sock.connect((self.host, self.port))
        
        # Build 200-byte claim and download payloads
        claim_p = struct.pack('<IIIiI', self.session_id, 0, 0, 7, 0) + record.remote_path.encode('latin1').ljust(108, b'\x00') + record.st_raw + record.et_raw + b'\x00'*24
        claim_p = claim_p.ljust(200, b'\x00')
        
        dl_p = struct.pack('<IIIiI', self.session_id, 0, 0, 8, 0) + record.remote_path.encode('latin1').ljust(108, b'\x00') + record.st_raw + record.et_raw + b'\x00'*24
        dl_p = dl_p.ljust(200, b'\x00')
        
        # 1. Claim on Data Socket
        data_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_CLAIM_REQ, claim_p, self.session_id, 0))
        d_hdr = self._recv_exact(data_sock, 20)
        _, _, _, _, _, _, _, d_len = NetSdkPacket.unpack_header(d_hdr)
        self._recv_exact(data_sock, d_len)
        
        # 2. Start Download on Control Socket
        self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_DOWNLOAD_REQ, dl_p, self.session_id, 2))
        c_hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, c_len = NetSdkPacket.unpack_header(c_hdr)
        self._recv_exact(self.ctrl_sock, c_len)
        
        # 3. Stream data chunks
        total_downloaded = 0
        target_size = max_bytes if max_bytes else record.size_kb * 1024
        
        with open(destination_path, 'wb') as f_out:
            t0 = time.time()
            chunk_num = 0
            while total_downloaded < target_size:
                try:
                    hdr = self._recv_exact(data_sock, 20)
                except:
                    break
                _, _, _, _, _, _, ptype, plen = NetSdkPacket.unpack_header(hdr)
                if ptype != NetSdkPacket.TYPE_DATA_CHUNK:
                    break
                chunk = self._recv_exact(data_sock, plen)
                f_out.write(chunk)
                total_downloaded += len(chunk)
                chunk_num += 1
                
                if progress_callback:
                    pct = min(100, int((total_downloaded / target_size) * 100)) if target_size else 0
                    speed = (total_downloaded / (1024*1024)) / max(0.001, time.time() - t0)
                    progress_callback(pct, total_downloaded, speed)
                    
        data_sock.close()
        return total_downloaded > 0

    def get_time(self) -> dict:
        """Queries the current system time from the DVR RTC."""
        payload = json.dumps({"Name": "OPTimeQuery", "SessionID": f"0x{self.session_id:08X}"}).encode('ascii') + b'\n\x00'
        self.ctrl_sock.sendall(NetSdkPacket.pack(1452, payload, self.session_id, 10))
        hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        if plen >= 44:
            y, m, d, dow, h, mn, s = struct.unpack('<7I', resp[16:44])
            return {"year": y, "month": m, "day": d, "hour": h, "minute": mn, "second": s, "formatted": f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mn:02d}:{s:02d}"}
        return {}

    def set_time(self, time_str: str) -> bool:
        """Sets the DVR system clock (format: 'YYYY-MM-DD HH:MM:SS')."""
        payload = json.dumps({"Name": "OPTimeSetting", "SessionID": f"0x{self.session_id:08X}", "OPTimeSetting": time_str}).encode('ascii') + b'\n\x00'
        self.ctrl_sock.sendall(NetSdkPacket.pack(1450, payload, self.session_id, 11))
        hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        return b'"Ret": 100' in resp or b'"Ret":100' in resp

    def get_channel_titles(self) -> list:
        """Queries OSD camera channel titles."""
        payload = json.dumps({"Name": "ChannelTitle", "SessionID": f"0x{self.session_id:08X}"}).encode('ascii') + b'\n\x00'
        self.ctrl_sock.sendall(NetSdkPacket.pack(1046, payload, self.session_id, 12))
        hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        try:
            data = json.loads(resp.rstrip(b'\x00\r\n').decode('utf-8', errors='replace'))
            return data.get("ChannelTitle", [])
        except:
            return []

    def set_channel_titles(self, titles: list) -> bool:
        """Updates OSD camera channel titles."""
        payload = json.dumps({"Name": "ChannelTitle", "SessionID": f"0x{self.session_id:08X}", "ChannelTitle": titles}).encode('ascii') + b'\n\x00'
        self.ctrl_sock.sendall(NetSdkPacket.pack(1046, payload, self.session_id, 13))
        hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        return b'"Ret": 100' in resp or b'"Ret":100' in resp

    def get_storage_info(self) -> list:
        """Queries hard drive partitions, total capacity and remaining free space."""
        payload = json.dumps({"Name": "StorageInfo", "SessionID": f"0x{self.session_id:08X}"}).encode('ascii') + b'\n\x00'
        self.ctrl_sock.sendall(NetSdkPacket.pack(1020, payload, self.session_id, 14))
        hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        try:
            data = json.loads(resp.rstrip(b'\x00\r\n').decode('utf-8', errors='replace'))
            return data.get("StorageInfo", [])
        except:
            return []

    def reboot(self) -> bool:
        """Remotely reboots the DVR."""
        payload = json.dumps({"Name": "OPMachine", "SessionID": f"0x{self.session_id:08X}", "OPMachine": {"Action": "Reboot"}}).encode('ascii') + b'\n\x00'
        self.ctrl_sock.sendall(NetSdkPacket.pack(1450, payload, self.session_id, 15))
        hdr = self._recv_exact(self.ctrl_sock, 20)
        _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
        resp = self._recv_exact(self.ctrl_sock, plen)
        return b'"Ret": 100' in resp or b'"Ret":100' in resp

    def close(self):
        if self.ctrl_sock:
            try: self.ctrl_sock.close()
            except: pass

    def _recv_exact(self, sock, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection lost")
            buf.extend(chunk)
        return bytes(buf)

if __name__ == '__main__':
    # Configuration - Change to your DVR details:
    DVR_IP = "192.168.1.100"
    DVR_PORT = 34567
    DVR_USER = "admin"
    DVR_PASS = ""  # Default Xiongmai password is often blank

    client = PureDvrClient(DVR_IP, DVR_PORT)
    print("Connecting...")
    if client.connect(DVR_USER, DVR_PASS):
        print(f"Connected! Session ID: 0x{client.session_id:X}\n")
        
        # Test 1: Query Device RTC Time
        dvr_time = client.get_time()
        print(f"Device RTC Time: {dvr_time.get('formatted')}")
        
        # Test 2: Query Channel Titles
        titles = client.get_channel_titles()
        print(f"Channel Titles: {titles}")
        
        # Test 3: Query Storage
        storage = client.get_storage_info()
        print(f"Storage Info: {storage}\n")

        # Test 4: Query Records
        files = client.search_files(channel=0, year=2026, month=10, day=13)
        print(f"Found {len(files)} files on Channel 1:")
        for idx, f in enumerate(files[:5]):
            print(f"  [{idx+1:2d}] {f.remote_path} ({f.size_mb:.1f} MB)")
        client.close()
    else:
        print("Login failed.")
