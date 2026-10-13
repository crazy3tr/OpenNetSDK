# Port 34567 Binary Wire Protocol Specification (Clean Room)

This document specifies the exact TCP wire protocol used by Xiongmai / Sofia / NetSDK CCTV DVR systems over **port 34567** (or forwarded NAT ports).

By implementing this specification, applications can connect, authenticate, search records, and download or stream video on **any operating system** (Android, Linux, macOS, iOS, Windows) without any native vendor DLLs (`NetSdkModule.dll`, ActiveX, etc.).

---

## 1. Protocol Overview

- **Transport:** TCP Stream Socket
- **Architecture:** Dual-Socket:
  1. **Control Socket:** Handles Session Authentication (Login/Logout), Keepalives, Device Config, and File Search.
  2. **Data Socket:** Handles Media Streaming, High-Speed Video Chunk Delivery, and Playback.
- **Byte Order:** Little-Endian for all integers.
- **Payload Format:** Strict **Binary C Structs** for core operations (Login, Search, Download Claim, Playback). Many firmwares reject JSON logins with code `205`.

---

## 2. Standard 20-Byte Packet Header

Every message exchanged between Client and DVR begins with this 20-byte header:

```c
struct NetSdkHeader {
    uint8_t  magic;       // 0xFF
    uint8_t  version;     // 0x00 = Client -> DVR, 0x01 = DVR -> Client
    uint16_t reserved;    // 0x0000
    uint32_t session_id;  // Assigned by DVR during Login response
    uint32_t sequence;    // Monotonically increasing sequence number
    uint8_t  flag0;       // 0x00
    uint8_t  flag1;       // 0x00
    uint16_t packet_type; // Command Type ID (e.g. 1000, 1440, 1420)
    uint32_t payload_len; // Length of payload following this 20-byte header
};
```

---

## 3. Authentication & Sofia Password Hash

### A. Password Hashing Algorithm ("Sofia Hash")
Xiongmai devices do not send passwords in plaintext. Passwords are transformed using a custom MD5-based Base62 reduction:

```python
import hashlib

def sofia_hash(password: str) -> str:
    md5_digest = hashlib.md5(password.encode('utf-8')).digest()
    base62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    # Process 8 consecutive byte pairs
    return "".join(base62[(md5_digest[2*i] + md5_digest[2*i+1]) % 62] for i in range(8))
```
*Example:* Password `"123456"` produces Sofia hash `"nTBCS19C"` (or empty password `""` produces `"tlJwpbo6"`).

### B. Login Request (Type 1000)
- **Header:** `Magic=0xFF00, SessionID=0, Type=1000, Length=72`
- **Payload (72 bytes):**
  - `0x00..0x1F` (32 bytes): Username (ANSI, null-padded, e.g. `admin\0...`)
  - `0x20..0x3F` (32 bytes): Hashed password (ANSI, null-padded, e.g. `nTBCS19C\0...`)
  - `0x40..0x43` (4 bytes): Login Type (`int32 = 1`)
  - `0x44..0x47` (4 bytes): Client Type (`int32 = 2`)

> [!NOTE]
> Sending a JSON login (`{"EncryptType":"MD5", ...}`) returns status code **205** (Format Rejected) regardless of credentials on modern firmware. The binary 72-byte payload must be used.

### C. Login Response (Type 1001)
- **Header:** `Magic=0xFF01, Type=1001, Length=24`
- **Payload (24 bytes):**
  - Offset `0x08`: `uint32 status` (`100` = Success, `203` = Password Error, `205` = Format Error)
  - Offset `0x10`: `uint32 session_id` (Active Session ID)

---

## 4. Hard Disk File Search (Type 1440 / 1441)

### A. Search Request (Type 1440)
- **Header:** `Magic=0xFF00, SessionID=SESS, Seq=1, Type=1440, Length=140`
- **Payload (140 bytes):**
  - `0x00`: `uint32 session_id`
  - `0x04`: `uint32 channel_index` (0-based)
  - `0x08..0x0F`: `uint64 0` (Padding)
  - `0x10..0x1F`: `char[16] "h264"` (Stream format)
  - `0x28`: `uint32 0x2A` (`'*'` mask for all record types)
  - `0x48`: `uint32 0xFFFF`
  - `0x4C..0x63`: Start Time (6 × `int32`: Year, Month, Day, Hour, Min, Sec)
  - `0x6C..0x83`: End Time (6 × `int32`: Year, Month, Day, Hour, Min, Sec)

### B. Search Response (Type 1441)
- **Header:** `Magic=0xFF01, SessionID=SESS, Type=1441, Length=N`
- **Payload:**
  - `0x00`: `uint32 session_id`
  - `0x04`: `uint32 status` (`100` = Success, `119` = Query matched 0 files)
  - `0x08..0x0F`: `uint64 reserved`
  - `0x10`: `uint32 file_count` (Number of records found)
  - `0x14..0x17`: `uint32 reserved`
  - `0x18..End`: Array of **184-byte record structs** (Stride = 184 bytes):
    - `+0x00`: `int32 channel_index` (0-based)
    - `+0x04`: `uint32 file_size_kb` (File size in Kilobytes)
    - `+0x08`: `char[108] remote_file_path` (e.g. `/idea0/YYYY-MM-DD/001/HH.MM.SS-HH.MM.SS[H][@hex][0].h264`)
    - `+0x74`: `byte[24] st_raw` (Raw Start Time block - pass through verbatim to download)
    - `+0x8C`: `byte[24] et_raw` (Raw End Time block - pass through verbatim to download)
    - `+0xA4`: `byte[20] flags_and_padding`

> [!TIP]
> The filename format `/idea0/YYYY-MM-DD/<chan3>/HH.MM.SS-HH.MM.SS[...]` contains the exact start and end times in string format (e.g. `17.00.00-18.00.00`). Use string parsing on the path for filtering, but preserve the verbatim 24-byte `st_raw` and `et_raw` structs for the download claim packet.

---

## 5. Dual-Socket File Download Handshake

Downloading directly from internal storage requires establishing a second TCP connection (`DataSocket`):

```mermaid
sequenceDiagram
    participant Client
    participant DVR_Control as DVR (Control Socket)
    participant DVR_Data as DVR (Data Socket)

    Client->>DVR_Control: Connect & Login (Type 1000)
    DVR_Control-->>Client: Login OK (SessionID = 0xCE)
    Client->>DVR_Control: Search Files (Type 1440)
    DVR_Control-->>Client: File List (Type 1441)

    Note over Client,DVR_Data: Dual-Socket Handshake
    Client->>DVR_Data: Connect to port 34567
    Client->>DVR_Data: Send Claim (Type 1424, Action = 7)
    DVR_Data-->>Client: Claim Accepted (Type 1425)
    Client->>DVR_Control: Send Download Start (Type 1420, Action = 8)
    DVR_Control-->>Client: Download Started (Type 1421)

    Note over Client,DVR_Control: CRITICAL: KeepAlive on Control Socket
    par Media Streaming & KeepAlive
        loop Every 2 Seconds
            Client->>DVR_Control: KeepAlive Ping (Type 1006)
            DVR_Control-->>Client: KeepAlive ACK (Type 1007)
        end
    and Video Transfer
        loop Video Chunks
            DVR_Data-->>Client: Chunk #0 (Type 1426, Len = 32768)
            DVR_Data-->>Client: Chunk #1 (Type 1426, Len = 32768)
            DVR_Data-->>Client: Chunk #N (Type 1426, Len = 32768)
        end
    end
```

### Video Data Chunks (Type 1426)
- Each chunk received over `DataSocket` starts with the 20-byte `NetSdkHeader`:
  - `Type = 1426` (`0x0592`)
  - `Length = 32768` (32 KB payload)
- Payload consists of raw H.264 elementary stream data chunks.
- Writing these payloads sequentially yields the complete, original `.h264` video file identical to the DVR internal storage.

---

## 6. Critical Operational Field Findings

### A. The ~47 MB Truncation Trap (Mandatory KeepAlive)
Xiongmai DVRs run an internal activity watchdog on the main **Control Socket**. 
- During a high-speed download on the **Data Socket**, if no packets are sent over the **Control Socket** for ~30 seconds, the DVR assumes the client disconnected and stops transmitting chunks.
- Over a standard 1.5 MB/s connection, 30 seconds corresponds exactly to **~47 MB**.
- **Fix:** Spawn a background timer/thread sending packet type `1006` (`KeepAlive`) every **2 seconds** on the control socket throughout the entire file download.

### B. Single Playback / Download Slot
Embedded DVR SoCs (HiSilicon Hi3520/Hi3521) allocate only **one playback/download DSP channel**:
- Only one download or playback stream can run concurrently.
- If a socket is abruptly disconnected mid-transfer, the DVR holds the slot in a busy state for 1–3 minutes until its internal TCP timeout expires. During this window, new claims return success but no data is transmitted.
- **Best Practice:** Serialize all downloads sequentially using mutexes/locks. Never terminate sockets mid-stream if avoidable.

---

## 7. Observed Status & Return Codes (`uint32`)

| Code | Name | Description |
|:---:|:---|:---|
| **100** | `NET_SUCCESS` | Command completed successfully. |
| **107** | `NET_NO_PERMISSION` | The current session does not have administrative rights for this operation. |
| **119** | `NET_FILE_NOT_FOUND` | Search executed properly but matched **0 files** (not a network or protocol failure). |
| **203** | `NET_PASSWORD_ERROR` | Incorrect password provided in login struct. |
| **205** | `NET_LOGIN_FORMAT_ERROR` | DVR rejected login format (e.g., received JSON instead of 72-byte binary struct). |
| **512 / 607** | `NET_NOT_SUPPORT` | Command or subsystem not supported on this device/firmware. |

---

## 8. H.264 Elementary Stream to MP4 Remuxing

The downloaded stream is a raw Annex-B H.264 elementary stream lacking container timestamps.

### ⚠️ Common FFmpeg Mistake:
```bash
# WRONG - produces broken ~2-second duration because h264 demuxer ignores -framerate
ffmpeg -framerate 25 -i input.h264 -c copy output.mp4
```

### ✅ Correct FFmpeg Invocation:
```bash
# CORRECT - forces input demuxer frame rate before -i
ffmpeg -y -r 25 -i input.h264 -c copy output.mp4
```
Setting `-r 25` **before** `-i` ensures FFmpeg calculates correct Presentation Time Stamps (PTS), yielding exact playback duration (e.g. 3600 seconds for a 1-hour segment).
