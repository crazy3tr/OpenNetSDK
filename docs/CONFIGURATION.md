# DVR Configuration & Device Management Guide

This document specifies how to programmatically control every setting and hardware feature of Xiongmai / Sofia / NetSDK CCTV DVRs (port 34567).

---

## 1. System Date & Time Management

### A. Query Device Time (`OPTimeQuery`, Type 1452)
- **Request Type:** `1452`
- **Request Payload:** `{"Name": "OPTimeQuery", "SessionID": "0x<SESSION_ID>"}\n\0`
- **Response Type:** `1453`
- **Response Binary Layout (48 bytes):**
  - Offset `0x00`: `uint32 session_id`
  - Offset `0x04`: `uint32 status` (`100` = Success)
  - Offset `0x10`: `uint32 year` (e.g. `2026`)
  - Offset `0x14`: `uint32 month` (1 - 12)
  - Offset `0x18`: `uint32 day` (1 - 31)
  - Offset `0x1C`: `uint32 day_of_week` (0 = Sunday .. 6 = Saturday)
  - Offset `0x20`: `uint32 hour` (0 - 23)
  - Offset `0x24`: `uint32 minute` (0 - 59)
  - Offset `0x28`: `uint32 second` (0 - 59)

### B. Synchronize / Set Device Time (`OPTimeSetting`, Type 1450)
- **Request Type:** `1450`
- **Request Payload:**
  ```json
  {
    "Name": "OPTimeSetting",
    "SessionID": "0x<SESSION_ID>",
    "OPTimeSetting": "2026-10-13 18:00:00"
  }
  ```
- **Response:** `{"Ret": 100}` (Status 100 indicates real-time hardware RTC updated).

---

## 2. Channel Titles (Camera Names & OSD)

### A. Query Channel Names (`ChannelTitle`, Type 1046)
- **Request Type:** `1046`
- **Request Payload:** `{"Name": "ChannelTitle", "SessionID": "0x<SESSION_ID>"}\n\0`
- **Response JSON:**
  ```json
  {
    "ChannelTitle": [
      "GIRIS-Ç",
      "CAM02",
      "CAM03",
      "CAM04"
    ],
    "Ret": 100
  }
  ```

### B. Update Channel Name (`ChannelTitle`, Type 1046)
- **Request Type:** `1046`
- **Request Payload:**
  ```json
  {
    "Name": "ChannelTitle",
    "SessionID": "0x<SESSION_ID>",
    "ChannelTitle": [
      "KASA",
      "DEPO",
      "GIRIS",
      "OTOPARK"
    ]
  }
  ```

---

## 3. Video Encoding, Resolution & Bitrate (`Simplify.Encode`)

### A. Query Current Video Profile (`Simplify.Encode`, Type 1042)
- **Request Type:** `1042`
- **Request Payload:** `{"Name": "Simplify.Encode", "SessionID": "0x<SESSION_ID>"}\n\0`
- **Response JSON Structure:**
  ```json
  {
    "Simplify.Encode": [
      {
        "MainFormat": {
          "Video": {
            "Resolution": "1080N",
            "FPS": 25,
            "Quality": 4,
            "BitRate": 2048,
            "BitRateControl": "VBR",
            "Compression": "H.264"
          }
        },
        "ExtraFormat": {
          "Video": {
            "Resolution": "CIF",
            "FPS": 12,
            "BitRate": 384,
            "Compression": "H.264"
          }
        }
      }
    ],
    "Ret": 100
  }
  ```

### B. Supported Values
- **Resolutions:** `1080N` (944x1080), `720P` (1280x720), `960H` (960x576), `D1` (704x576), `CIF` (352x288)
- **Framerate (FPS):** `1` to `25` (or `30` in NTSC mode)
- **Bitrate:** `512`, `1024`, `1536`, `2048`, `3072`, `4096` Kbps
- **Rate Control:** `CBR` (Constant Bitrate) or `VBR` (Variable Bitrate)

---

## 4. Recording Schedule & Plan (`Record`)

Controls automated 24/7 video recording vs motion-activated recording.

- **Command Name:** `Record` (Type 1042 for Get, Type 1040 for Set)
- **Payload Parameters:**
  - `Mask`: 7 arrays (Monday through Sunday), each containing 6 timing masks.
  - `PreRecord`: Seconds buffered prior to event trigger (e.g. `5` seconds).
  - `RecordLength`: Segment block split size in minutes (`30`, `45`, `60`).
  - `RecordMode`:
    - `"ConfigDetect"`: Motion detection recording only.
    - `"Regular"`: Continuous 24/7 scheduled recording.
    - `"Manual"`: Force continuous recording on all channels.
    - `"Closed"`: Disable recording.

---

## 5. Storage & Hard Drive Management (`StorageInfo` / `OPStorageManager`)

### A. Query Hard Drive Space & Partitions (`StorageInfo`, Type 1020)
- **Request Type:** `1020`
- **Response JSON:**
  ```json
  {
    "StorageInfo": [
      {
        "PartNumber": 1,
        "TotalSpace": 953869,
        "RemainSpace": 142350,
        "Status": "OK",
        "IsCurrent": true
      }
    ],
    "Ret": 100
  }
  ```
  *(Sizes expressed in Megabytes)*

### B. Format Hard Drive (`OPStorageManager`, Type 1450)
- **Payload:**
  ```json
  {
    "Name": "OPStorageManager",
    "SessionID": "0x<SESSION_ID>",
    "OPStorageManager": {
      "Action": "Clear",
      "PartNo": 0,
      "SerialNo": 0
    }
  }
  ```

---

## 6. Motion Detection & Alarms (`MotionDetect`)

- **Command Name:** `MotionDetect` (Type 1042 for Get, Type 1040 for Set)
- **Payload Parameters:**
  - `Enable`: `true` / `false`
  - `Level`: Detection sensitivity from `1` (lowest) to `6` (highest).
  - `Region`: Binary grid bitmask defining active detection zones on the camera view.
  - `EventHandler`: Action matrix when motion is triggered:
    - `"RecordMask"`: Channels to start recording.
    - `"AlarmOut"`: Hardware relay trigger.
    - `"Buzzer"`: DVR motherboard beeper on/off.
    - `"Mail"`: Send snapshot over SMTP.

---

## 7. Virtual Front-Panel Key Simulation (`ClickKey` / `OPNetKeyboard`)

Allows controlling the DVR's on-screen monitor display (OSD) as if pressing the physical front-panel buttons or IR remote control:

| Key Name | Code | Action |
|----------|------|--------|
| `Menu` | `"M"` | Opens / closes system menu on local monitor |
| `Enter` | `"E"` | Confirms selection / opens dialog |
| `Esc` | `"Esc"` | Cancels / goes back one level |
| `Up` | `"U"` | Directional Up |
| `Down` | `"D"` | Directional Down |
| `Left` | `"L"` | Directional Left |
| `Right` | `"R"` | Directional Right |
| `1` .. `4` | `"1"`..`"4"` | Switch full-screen camera channel |

---

## 8. System Power & Maintenance (`OPMachine`)

- **Command Name:** `OPMachine` (Type 1450)
- **Actions:**
  - **Reboot:**
    ```json
    {"Name": "OPMachine", "SessionID": "0x<SESSION_ID>", "OPMachine": {"Action": "Reboot"}}
    ```
  - **Shutdown:**
    ```json
    {"Name": "OPMachine", "SessionID": "0x<SESSION_ID>", "OPMachine": {"Action": "Shutdown"}}
    ```
  - **Restore Factory Defaults:**
    ```json
    {"Name": "OPDefaultConfig", "SessionID": "0x<SESSION_ID>", "OPDefaultConfig": {"AllConfig": true}}
    ```
