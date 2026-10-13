# NetSdkModule.dll Export Catalog

This document indexes all 71 exported functions in `NetSdkModule.dll`, categorized by functional domain.

---

## 1. Initialization, Authentication & Session
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_Init` | Initializes the internal networking stack and memory pools. |
| `NET_SDK_Cleanup` | Releases all SDK resources and sockets. |
| `NET_SDK_Login` | Authenticates with the DVR via IP, port, username, password. Returns session ID. |
| `NET_SDK_Logout` | Gracefully closes the session. |
| `NET_SDK_GetLastError` | Returns the error code of the last failed operation. |
| `NET_SDK_SetConnectTime` | Configures socket connection and response timeouts. |
| `NET_SDK_GetOEMInfo` | Retrieves OEM branding and hardware identifier. |

---

## 2. Hard Disk Recording, File Search & Download
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_FindFileByName` | Queries the DVR hard disk catalogue for recorded video files in a time window. |
| `NET_SDK_FindFileByTime` | Queries the 24-hour recording schedule bitmap for timeline visualization. |
| `NET_SDK_GetFileByName` | Downloads a specific recorded video file from the internal hard drive storage. |
| `NET_SDK_GetFileByTime` | Downloads recorded stream covering a specific time range. |
| `NET_SDK_GetFileByTime_V2` | Extended time range download method. |
| `NET_SDK_GetFileByTime_V3` | High-precision time range download method. |
| `_NET_SDK_GetFileByNameV2@20` | Secondary entry point for file download. |
| `NET_SDK_GetDownloadPos` | Returns the download progress percentage (0 - 100) or error code (< 0). |
| `NET_SDK_StopGetFile` | Cancels or finalizes an active file download handle. |

---

## 3. Remote Playback (Streaming Recorded Video)
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_PlayBackByName` | Starts remote video playback of a file by name. |
| `NET_SDK_PlayBackByName_Ex` | Extended playback by name with custom buffer size. |
| `NET_SDK_PlayBackByTime` | Starts remote video playback streaming from a specific timestamp. |
| `NET_SDK_PlayBackByTime_Ex` | Extended playback by timestamp. |
| `NET_SDK_PlayBackControl` | Play, Pause, Fast Forward (2x, 4x, 8x), Slow Motion, Seek. |
| `NET_SDK_StopPlayBack` | Stops playback stream. |

---

## 4. Live Video Streaming & Snapshots
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_RealPlay` | Initiates a live video stream from a specified camera channel. |
| `NET_SDK_StopRealPlay` | Closes an active live video stream. |
| `NET_SDK_PauseRealPlay` | Temporarily freezes/pauses live stream processing. |
| `NET_SDK_SetRealDataCallBack` | Registers callback receiving raw H.264 stream frames (NALUs). |
| `NET_SDK_SetRealDataCallBack_EX` | Extended callback providing timestamps and frame headers. |
| `NET_SDK_DelRealDataCallBack` | Unregisters stream callback. |
| `NET_SDK_DelRealDataCallBack_EX` | Unregisters extended callback. |
| `NET_SDK_MakeKeyFrame` | Requests an immediate I-Frame / IDR keyframe from the encoder. |
| `NET_SDK_CatchPic` | Captures a live JPEG snapshot and saves directly to disk. |
| `NET_SDK_CatchPicInBuffer` | Captures a live snapshot directly into a memory buffer. |

---

## 5. Two-Way Audio (Intercom / Talk)
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_StartVoiceCom_MR` | Opens a two-way audio voice intercom channel with the DVR. |
| `NET_SDK_StopVoiceCom` | Terminates the voice communication channel. |
| `NET_SDK_VoiceComSendData` | Sends local microphone audio packets to the DVR speaker. |
| `NET_SDK_EnableAudioSend` | Toggles local audio transmission on/off. |
| `NET_SDK_SetTalkMode` | Configures audio encoding mode (G.711A, G.711U, PCM). |

---

## 6. PTZ (Pan / Tilt / Zoom) Control
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_PTZControl` | Sends Pan, Tilt, Zoom, Focus, Iris, and Preset commands to motorized cameras. |

---

## 7. Device Configuration, Alarms & Maintenance
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_GetDevConfig` | Queries device configuration (video parameters, network, channels). |
| `NET_SDK_SetDevConfig` | Applies new device configuration. |
| `NET_SDK_SetConfigOverNet` | Applies network settings remotely. |
| `NET_SDK_SetSystemDateTime` | Synchronizes the DVR system clock with external date/time. |
| `NET_SDK_GetDVRWorkState` | Queries DVR runtime health, channel status, disk status, and temperature. |
| `NET_SDK_StorageManage` | Partitions, formats, or manages internal hard disk drives. |
| `NET_SDK_ControlDVR` | Issues system commands (Reboot, Shutdown). |
| `NET_SDK_ClickKey` | Simulates front panel / IR remote control key presses. |
| `NET_SDK_StartDVRRecord` | Manually triggers recording on a channel. |
| `NET_SDK_StopDVRRecord` | Stops manual recording. |
| `NET_SDK_FindDVRLog` | Queries system and security event logs from the DVR. |
| `NET_SDK_StartUpgrade` | Initiates remote firmware upgrade. |
| `NET_SDK_SendUpgradeData` | Transmits firmware update binary blocks. |
| `NET_SDK_GetUpgradeState` | Monitors firmware upgrade progress. |
| `NET_SDK_CloseUpgradeHandle` | Closes firmware upgrade handle. |

---

## 8. Network Device Discovery & Alarms
| Ordinal / Function | Purpose |
|--------------------|---------|
| `NET_SDK_SearchDevice` | Broadcasts UDP discovery packets to locate DVRs on the local subnet. |
| `NET_SDK_SearchDeviceByRemote` | Searches for DVRs across remote IP ranges. |
| `NET_SDK_GetDDNSInfo` | Queries dynamic DNS configuration. |
| `NET_SDK_InitGlink` / `NET_SDK_AddPreLink` | P2P / Cloud gateway linkage routines. |
| `NET_SDK_SetupAlarmChan` | Subscribes to alarm events (Motion, Video Loss, Sensor input). |
| `NET_SDK_CloseAlarmChan` | Unsubscribes from alarm events. |
| `NET_SDK_StartAlarmCenterListen` | Listens for inbound alarm notifications from the DVR. |
| `NET_SDK_StopAlarmCenterListen` | Stops alarm center listener. |
| `NET_SDK_SetDVRMessCallBack` | Sets callback function for real-time alarm event notifications. |
| `NET_SDK_SendNetAlarmMsg` | Emits custom alarm message to the DVR. |
| `NET_SDK_SerialRead` | Reads data from the DVR's RS485 / RS232 serial COM port. |
| `NET_SDK_SerialWrite` | Writes data to the DVR's RS485 / RS232 serial COM port. |
