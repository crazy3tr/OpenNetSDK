#!/usr/bin/env python3
"""
OpenXM-DVR - Pure Python Client (Zero Dependencies, Zero DLLs)
Works across Linux, macOS, Windows, Android (Termux/Kivy), Raspberry Pi.

Clean-room implementation of the Xiongmai / Sofia / NetSDK binary protocol.
"""

from __future__ import annotations
import socket
import struct
import hashlib
import json
import os
import sys
import time
import re
import threading
import subprocess
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sofia_hash(password: str) -> str:
    """Computes Xiongmai/Sofia password hash for port 34567."""
    md5 = hashlib.md5(password.encode('utf-8')).digest()
    base62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(base62[(md5[2*i] + md5[2*i+1]) % 62] for i in range(8))

def convert_to_mp4(input_h264_path: str, output_mp4_path: str, fps: int = 25, ffmpeg_path: str = "ffmpeg") -> bool:
    """
    Losslessly remuxes raw H.264 elementary streams into standard MP4 containers using ffmpeg.
    
    CRITICAL FFMPEG PARAMETER RULE:
    The input frame rate '-r <fps>' MUST be placed BEFORE '-i'. 
    Using '-framerate' after '-i' produces corrupted MP4 durations (~2 seconds) because 
    the raw H.264 elementary demuxer ignores image2 parameters.
    """
    cmd = [ffmpeg_path, "-y", "-r", str(fps), "-i", input_h264_path, "-c", "copy", output_mp4_path]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode == 0
    except Exception:
        return False

class NetSdkPacket:
    MAGIC_REQ = 0xFF00
    MAGIC_RESP = 0xFF01
    
    TYPE_LOGIN_REQ = 1000
    TYPE_LOGIN_RESP = 1001
    TYPE_KEEPALIVE_REQ = 1006
    TYPE_KEEPALIVE_RESP = 1007
    TYPE_STORAGE_INFO_REQ = 1020
    TYPE_CONFIG_SET = 1040
    TYPE_CONFIG_GET = 1042
    TYPE_CHANNELTITLE_GET = 1046
    TYPE_CHANNELTITLE_BINARY = 1048
    TYPE_SEARCH_REQ = 1440
    TYPE_SEARCH_RESP = 1441
    TYPE_CLAIM_REQ = 1424
    TYPE_CLAIM_RESP = 1425
    TYPE_DOWNLOAD_REQ = 1420
    TYPE_DOWNLOAD_RESP = 1421
    TYPE_DATA_CHUNK = 1426
    TYPE_TIME_SETTING = 1450
    TYPE_TIME_QUERY = 1452
    TYPE_TIME_RESP = 1453

    # Protocol Return / Status codes
    RET_SUCCESS = 100
    RET_NO_PERMISSION = 107
    RET_FILE_NOT_FOUND = 119
    RET_PASSWORD_ERROR = 203
    RET_LOGIN_FORMAT_ERROR = 205
    RET_NOT_SUPPORTED = 512

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
        
        self.date_str = ""
        self.start_time = ""
        self.end_time = ""
        self._parse_path()

    def _parse_path(self):
        # Format: /idea0/YYYY-MM-DD/<chan3>/HH.MM.SS-HH.MM.SS[H][@<hexid>][0].h264
        m = re.search(r'(\d{4}-\d{2}-\d{2})/[^/]+/(\d{2}\.\d{2}\.\d{2})-(\d{2}\.\d{2}\.\d{2})', self.remote_path)
        if m:
            self.date_str = m.group(1)
            self.start_time = m.group(2).replace('.', ':')
            self.end_time = m.group(3).replace('.', ':')
        elif len(self.st_raw) >= 24 and len(self.et_raw) >= 24:
            try:
                sy, sm, sd, sh, smn, ss = struct.unpack('<6i', self.st_raw[:24])
                ey, em, ed, eh, emn, es = struct.unpack('<6i', self.et_raw[:24])
                if 2000 <= sy <= 2099 and 1 <= sm <= 12 and 1 <= sd <= 31:
                    self.date_str = f"{sy:04d}-{sm:02d}-{sd:02d}"
                    self.start_time = f"{sh:02d}:{smn:02d}:{ss:02d}"
                    self.end_time = f"{eh:02d}:{emn:02d}:{es:02d}"
            except Exception:
                pass
        
    def __repr__(self):
        t_info = f" {self.start_time}-{self.end_time}" if self.start_time else ""
        return f"<RecordFile ch={self.channel}{t_info} size={self.size_mb:.1f}MB path={self.remote_path}>"

class PureDvrClient:
    def __init__(self, host: str, port: int = 34567):
        self.host = host
        self.port = port
        self.session_id = 0
        self.ctrl_sock = None
        self._ctrl_lock = threading.Lock()
        self._slot_lock = threading.Lock()

    def connect(self, username: str = "admin", password: str = "") -> bool:
        """Connects and authenticates with the DVR using binary credentials."""
        with self._ctrl_lock:
            self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ctrl_sock.settimeout(10.0)
            self.ctrl_sock.connect((self.host, self.port))
            
            # Build Binary Login Payload (72 bytes: 32 user + 32 pass_hash + 4 login_type + 4 client_type)
            hashed = sofia_hash(password)
            u_bytes = username.encode('ascii').ljust(32, b'\x00')
            p_bytes = hashed.encode('ascii').ljust(32, b'\x00')
            payload = u_bytes + p_bytes + struct.pack('<II', 1, 2)
            
            self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_LOGIN_REQ, payload))
            
            hdr = self._recv_exact(self.ctrl_sock, 20)
            m, v, sess, seq, f0, f1, ptype, plen = NetSdkPacket.unpack_header(hdr)
            resp = self._recv_exact(self.ctrl_sock, plen)
            
            status = struct.unpack('<I', resp[8:12])[0]
            if status == NetSdkPacket.RET_SUCCESS:
                self.session_id = sess
                return True
            return False

    def search_files(self, channel: int = 0, year: int | None = None, month: int | None = None, day: int | None = None, stride: int = 184) -> list:
        """
        Queries recording records for a specific day.
        Returns list of RecordFile objects.
        Stride defaults to 184 bytes per record struct.
        """
        if year is None or month is None or day is None:
            now = datetime.now()
            year = year if year is not None else now.year
            month = month if month is not None else now.month
            day = day if day is not None else now.day

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
        
        with self._ctrl_lock:
            self.ctrl_sock.settimeout(10.0)
            self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_SEARCH_REQ, bytes(payload), self.session_id, 1))
            
            hdr = self._recv_exact(self.ctrl_sock, 20)
            m, v, s, seq, f0, f1, ptype, plen = NetSdkPacket.unpack_header(hdr)
            resp = self._recv_exact(self.ctrl_sock, plen)
        
        status = struct.unpack('<I', resp[4:8])[0] if plen >= 8 else 0
        if status == NetSdkPacket.RET_FILE_NOT_FOUND:
            return []

        file_count = struct.unpack('<i', resp[16:20])[0] if plen >= 20 else 0
        records = []
        if file_count > 0:
            for i in range(file_count):
                rec = resp[24 + i*stride : 24 + (i+1)*stride]
                if len(rec) < 116:
                    continue
                ch = struct.unpack('<I', rec[0:4])[0]
                sz_kb = struct.unpack('<I', rec[4:8])[0]
                path = rec[8:116].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                st_raw = rec[116:140] if len(rec) >= 140 else b'\x00'*24
                et_raw = rec[140:164] if len(rec) >= 164 else b'\x00'*24
                records.append(RecordFile(ch, sz_kb, path, st_raw, et_raw))
        return records

    def download_file(self, record: RecordFile, destination_path: str, progress_callback=None, max_bytes=None) -> bool:
        """
        Downloads a file directly from DVR hard drive via secondary Data Socket.
        
        CRITICAL FIELD OBSERVATIONS IMPLEMENTED:
        1. KeepAlive on Control Socket: Without periodic Type 1006 keepalives on ctrl_sock,
           the DVR watchdog terminates the transfer at ~47 MB. A background keepalive thread
           maintains the session every 2 seconds.
        2. Single Playback/Download Slot: Embedded DVR firmware supports only one active
           download/playback at a time. This method locks `_slot_lock` to ensure sequential
           execution and clean teardown.
        """
        with self._slot_lock:
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_sock.settimeout(15.0)
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
            with self._ctrl_lock:
                self.ctrl_sock.settimeout(10.0)
                self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_DOWNLOAD_REQ, dl_p, self.session_id, 2))
                c_hdr = self._recv_exact(self.ctrl_sock, 20)
                _, _, _, _, _, _, _, c_len = NetSdkPacket.unpack_header(c_hdr)
                self._recv_exact(self.ctrl_sock, c_len)

            # 3. Background KeepAlive thread on Control Socket (prevents 47 MB timeout)
            stop_ka = threading.Event()
            ka_error = False

            def keepalive_loop():
                nonlocal ka_error
                seq_num = 100
                while not stop_ka.wait(2.0):
                    try:
                        with self._ctrl_lock:
                            ka_body = struct.pack('<IIII', self.session_id, 0, 0, 0)
                            self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_KEEPALIVE_REQ, ka_body, self.session_id, seq_num))
                            # Drain keepalive ACK
                            self.ctrl_sock.settimeout(2.0)
                            k_hdr = self._recv_exact(self.ctrl_sock, 20)
                            _, _, _, _, _, _, _, k_len = NetSdkPacket.unpack_header(k_hdr)
                            if k_len > 0:
                                self._recv_exact(self.ctrl_sock, k_len)
                            self.ctrl_sock.settimeout(None)
                            seq_num += 1
                    except Exception:
                        ka_error = True
                        break

            ka_thread = threading.Thread(target=keepalive_loop, daemon=True)
            ka_thread.start()

            # 4. Stream data chunks from Data Socket
            total_downloaded = 0
            target_size = max_bytes if max_bytes else record.size_kb * 1024
            
            try:
                with open(destination_path, 'wb') as f_out:
                    t0 = time.time()
                    while total_downloaded < target_size:
                        try:
                            hdr = self._recv_exact(data_sock, 20)
                        except Exception:
                            break
                        _, _, _, _, _, _, ptype, plen = NetSdkPacket.unpack_header(hdr)
                        if ptype != NetSdkPacket.TYPE_DATA_CHUNK:
                            break
                        chunk = self._recv_exact(data_sock, plen)
                        f_out.write(chunk)
                        total_downloaded += len(chunk)
                        
                        if progress_callback:
                            pct = min(100, int((total_downloaded / target_size) * 100)) if target_size else 0
                            speed = (total_downloaded / (1024*1024)) / max(0.001, time.time() - t0)
                            progress_callback(pct, total_downloaded, speed)
            finally:
                stop_ka.set()
                ka_thread.join(timeout=1.0)
                try:
                    data_sock.close()
                except Exception:
                    pass

            if progress_callback and target_size:
                progress_callback(100, total_downloaded, (total_downloaded / (1024*1024)) / max(0.001, time.time() - t0))

            # Allow up to 2KB rounding margin on DVR size reporting (since firmware rounds up to whole KB)
            min_expected = max(0, target_size - 2048) if target_size else 0
            if min_expected > 0:
                if ka_error and total_downloaded < min_expected:
                    return False
                return total_downloaded >= min_expected
            return total_downloaded > 0 and not ka_error

    def get_time(self) -> dict:
        """Queries the current system time from the DVR RTC."""
        with self._ctrl_lock:
            payload = json.dumps({"Name": "OPTimeQuery", "SessionID": f"0x{self.session_id:08X}"}, ensure_ascii=False).encode('utf-8') + b'\n\x00'
            self.ctrl_sock.settimeout(5.0)
            self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_TIME_QUERY, payload, self.session_id, 10))
            hdr = self._recv_exact(self.ctrl_sock, 20)
            _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
            resp = self._recv_exact(self.ctrl_sock, plen)
            if plen >= 44:
                y, m, d, dow, h, mn, s = struct.unpack('<7I', resp[16:44])
                return {"year": y, "month": m, "day": d, "hour": h, "minute": mn, "second": s, "formatted": f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mn:02d}:{s:02d}"}
            return {}

    def set_time(self, time_str: str) -> bool:
        """Sets the DVR system clock (format: 'YYYY-MM-DD HH:MM:SS')."""
        with self._ctrl_lock:
            payload = json.dumps({"Name": "OPTimeSetting", "SessionID": f"0x{self.session_id:08X}", "OPTimeSetting": time_str}, ensure_ascii=False).encode('utf-8') + b'\n\x00'
            self.ctrl_sock.settimeout(5.0)
            self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_TIME_SETTING, payload, self.session_id, 11))
            hdr = self._recv_exact(self.ctrl_sock, 20)
            _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
            resp = self._recv_exact(self.ctrl_sock, plen)
            return b'"Ret": 100' in resp or b'"Ret":100' in resp

    def get_channel_titles(self) -> list:
        """
        Queries OSD camera channel titles.
        Tries standard JSON config query (1042 CONFIG_GET) first, then falls back to binary slot blob (1048).
        """
        titles = []
        # Attempt 1: Standard JSON Config Query (Type 1042 CONFIG_GET)
        try:
            with self._ctrl_lock:
                self.ctrl_sock.settimeout(4.0)
                payload = json.dumps({"Name": "ChannelTitle", "SessionID": f"0x{self.session_id:08X}"}, ensure_ascii=False).encode('utf-8') + b'\n\x00'
                self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_CONFIG_GET, payload, self.session_id, 12))
                hdr = self._recv_exact(self.ctrl_sock, 20)
                _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
                resp = self._recv_exact(self.ctrl_sock, plen)
                data = json.loads(resp.rstrip(b'\x00\r\n').decode('utf-8', errors='replace'))
                titles = data.get("ChannelTitle", [])
                if titles:
                    return titles
        except Exception:
            pass

        # Attempt 2: Binary Config fallback (Type 1048, 64-byte aligned slot names)
        try:
            with self._ctrl_lock:
                self.ctrl_sock.settimeout(4.0)
                req_p = struct.pack('<IIII', self.session_id, 0, 0, 0)
                self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_CHANNELTITLE_BINARY, req_p, self.session_id, 13))
                hdr = self._recv_exact(self.ctrl_sock, 20)
                _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
                resp = self._recv_exact(self.ctrl_sock, plen)
                for offset in range(16, plen, 64):
                    raw_str = resp[offset:offset+64].split(b'\x00', 1)[0]
                    decoded = raw_str.decode('utf-8', errors='ignore').strip()
                    if decoded:
                        titles.append(decoded)
        except Exception:
            pass

        return titles

    def set_channel_titles(self, titles: list) -> bool:
        """Updates OSD camera channel titles."""
        with self._ctrl_lock:
            try:
                payload = json.dumps({"Name": "ChannelTitle", "SessionID": f"0x{self.session_id:08X}", "ChannelTitle": titles}, ensure_ascii=False).encode('utf-8') + b'\n\x00'
                self.ctrl_sock.settimeout(5.0)
                self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_CONFIG_SET, payload, self.session_id, 13))
                hdr = self._recv_exact(self.ctrl_sock, 20)
                _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
                resp = self._recv_exact(self.ctrl_sock, plen)
                return b'"Ret": 100' in resp or b'"Ret":100' in resp
            except Exception:
                return False

    def get_storage_info(self) -> list:
        """Queries hard drive partitions, total capacity and remaining free space."""
        try:
            with self._ctrl_lock:
                self.ctrl_sock.settimeout(4.0)
                payload = json.dumps({"Name": "StorageInfo", "SessionID": f"0x{self.session_id:08X}"}, ensure_ascii=False).encode('utf-8') + b'\n\x00'
                self.ctrl_sock.sendall(NetSdkPacket.pack(NetSdkPacket.TYPE_STORAGE_INFO_REQ, payload, self.session_id, 14))
                hdr = self._recv_exact(self.ctrl_sock, 20)
                _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
                resp = self._recv_exact(self.ctrl_sock, plen)
                data = json.loads(resp.rstrip(b'\x00\r\n').decode('utf-8', errors='replace'))
                return data.get("StorageInfo", [])
        except Exception:
            return []

    def reboot(self) -> bool:
        """Remotely reboots the DVR."""
        with self._ctrl_lock:
            payload = json.dumps({"Name": "OPMachine", "SessionID": f"0x{self.session_id:08X}", "OPMachine": {"Action": "Reboot"}}, ensure_ascii=False).encode('utf-8') + b'\n\x00'
            self.ctrl_sock.settimeout(5.0)
            self.ctrl_sock.sendall(NetSdkPacket.pack(1450, payload, self.session_id, 15))
            hdr = self._recv_exact(self.ctrl_sock, 20)
            _, _, _, _, _, _, _, plen = NetSdkPacket.unpack_header(hdr)
            resp = self._recv_exact(self.ctrl_sock, plen)
            return b'"Ret": 100' in resp or b'"Ret":100' in resp

    def close(self):
        with self._ctrl_lock:
            if self.ctrl_sock:
                try: self.ctrl_sock.close()
                except: pass
                self.ctrl_sock = None

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
        files = client.search_files(channel=0)
        print(f"Found {len(files)} files on Channel 1:")
        for idx, f in enumerate(files[:5]):
            print(f"  [{idx+1:2d}] {f.remote_path} ({f.size_mb:.1f} MB)")
        client.close()
    else:
        print("Login failed.")
