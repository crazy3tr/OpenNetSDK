# Native NetSDK Vendor Binaries (x86)

This repository provides a clean-room specification and client implementations licensed under the MIT License. In accordance with open-source licensing compliance, proprietary closed-source vendor binaries are not distributed within this repository.

## Do I need these DLLs?

- **Python Client (`python/pure_dvr_client.py`):** **NO.**  
  The Python client is a 100% clean-room, zero-dependency socket implementation of the NetSDK / Sofia protocol. It requires **no vendor DLLs** and runs natively across Linux, macOS, Android (via Termux/Kivy), Raspberry Pi, and Windows.

- **C# / .NET SDK (`src/NetDvrSdk/`):**  
  If you are using the C# P/Invoke wrapper (`NativeMethods.cs` calling `NET_SDK_Login`, `NET_SDK_FindFileByName`, `NET_SDK_GetFileByName`), place the official 32-bit (x86) vendor binaries from your hardware vendor SDK or CMS software into this folder:
  - `NetSdkModule.dll`
  - `ConfigureModule.dll`
  - `PlayBackModule.dll`
  - `PlaySdkModule.dll`
  - `StreamReaderModule.dll`
  - `DllDeinterlace.dll`
  - `hi_h264dec.dll`
