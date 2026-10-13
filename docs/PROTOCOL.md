# NetSDK (Port 34567) Protocol & Binary Specification

## 1. Network Architecture & Ports

CCTV DVRs based on Xiongmai (XM) / Sofia / HiSilicon firmware typically expose:

| Port | Service | Description |
|------|---------|-------------|
| **34567** | **NetSDK / DVR Protocol** | Primary binary media, stream, and control protocol. Used by CMS, mobile apps, and NetSDK. |
| **80** | **HTTP / Web Interface** | Legacy web interface (ActiveX / `WebCtrl.ocx`). |
| **554** | **RTSP (Optional)** | Real-Time Streaming Protocol (often disabled or basic). |

---

## 2. Reverse-Engineered Data Structures

### A. Session Login (`NET_SDK_Login`)
```c
int NET_SDK_Login(
    char* sDVRIP,
    int wDVRPort,
    char* sUserName,
    char* sPassword,
    void* lpDeviceInfo, // Allocate at least 4096 bytes
    int arg6,           // Set to 0
    int* pError,        // Pointer to int receiving error code (CRITICAL: cannot be NULL)
    int arg8,           // Set to 0
    int arg9            // Set to 0
);
```
> **Critical Finding**: Passing `NULL` (or `0`) for `pError` results in an immediate crash at `0x10006EB2` (`mov [edi], esi`) due to a NULL pointer dereference inside `NetSdkModule.dll`.

---

### B. File Search Query (`NET_SDK_FindFileByName`)
The search info structure passed to `NET_SDK_FindFileByName` is exactly **60 bytes** long:

| Offset | Type | Field Name | Description |
|--------|------|------------|-------------|
| `0x00` | `int32` | `nChannel` | 0-indexed channel number (Channel 1 = `0`, Channel 2 = `1`) |
| `0x04` | `int32` | `nFileType` | File type mask (`0` = All, `1` = Alarm/Motion `[H]`, `8` = Regular `[R]`) |
| `0x08` | `int32[6]` | `startTime` | Year, Month, Day, Hour, Minute, Second (6 × 4 bytes = 24 bytes) |
| `0x20` | `int32[6]` | `endTime` | Year, Month, Day, Hour, Minute, Second (6 × 4 bytes = 24 bytes) |
| `0x38` | `int32` | `reserved` | Reserved padding (`0`) |

---

### C. File Record Struct (`NET_SDK_REC_FILE`)
The file record buffer populated by `NET_SDK_FindFileByName` has a strict stride of **180 bytes (`0xB4`)** per record:

| Offset | Type | Field Name | Description |
|--------|------|------------|-------------|
| `0x00` | `int32` | `nChannel` | Channel index (e.g., `0`) |
| `0x04` | `int32` | `nFileSizeKB` | File size on internal disk in **Kilobytes (KB)** |
| `0x08` | `char[108]` | `sFileName` | Null-terminated internal DVR file path |
| `0x74` | `byte[64]` | `metaData` | Start/end timestamp structures & cluster metadata |

#### Internal DVR File Path Format
Example: `/idea0/2026-10-13/001/13.00.00-13.43.50[H][@11a6fb][0].h264`
- `/idea0/`: Internal mount point for Hard Disk 0.
- `2026-10-13`: Date of recording.
- `001`: 3-digit Channel ID (Channel 1).
- `13.00.00-13.43.50`: Start time (`13:00:00`) to End time (`13:43:50`).
- `[H]`: Recording trigger type:
  - `[H]`: Motion / Sensor Alarm trigger.
  - `[R]`: Continuous / Scheduled regular recording.
- `[@11a6fb][0]`: Internal disk sector/cluster address.

---

### D. File Download (`NET_SDK_GetFileByName`)
```c
int NET_SDK_GetFileByName(
    int lLoginID,
    void* lpFileDataRecord, // Pointer to the exact 180-byte record slice from FindFileByName
    char* sSavedFileName,   // Full destination path on local disk
    void* cbDownLoadPos,    // Optional callback or NULL
    void* dwUserData        // Optional user data or NULL
);
```
> **Key Finding**: `NET_SDK_GetFileByName` requires the pointer to the **180-byte record buffer**, NOT a string file path. Passing a string will fail with handle `0`.

---

## 3. Video Encoding & Stream Processing

- **Video Codec**: H.264 Elementary Stream (High Profile).
- **Resolution**: `944x1080` (AHD 1080N standard format). When played in a 16:9 container, it is scaled to full HD aspect ratio.
- **Framerate**: 25.0 FPS.
- **Lossless MP4 Packaging (Remuxing)**:
  Because the raw elementary stream lacks container PTS/DTS timestamps, standard players need a valid MP4 container. Using `ffmpeg`, conversion is instantaneous (0.2s) without re-encoding:
  ```bash
  ffmpeg -y -r 25 -i "input.h264" -c copy "output.mp4"
  ```
