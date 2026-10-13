using System;
using System.Runtime.InteropServices;

namespace NetDvrSdk
{
    internal static class NativeMethods
    {
        private const string DllName = "NetSdkModule.dll";

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern bool NET_SDK_Init(IntPtr cbDisConnect, IntPtr dwUser);

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern bool NET_SDK_Cleanup();

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
        public static extern int NET_SDK_Login(
            string sDVRIP,
            int wDVRPort,
            string sUserName,
            string sPassword,
            IntPtr lpDeviceInfo,
            int arg6,
            IntPtr pError,
            int arg8,
            int arg9
        );

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern bool NET_SDK_Logout(int lLoginID);

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern int NET_SDK_GetLastError();

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
        public static extern bool NET_SDK_GetOEMInfo(int lLoginID, byte[] pOEMInfo, int nBufLen);

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern bool NET_SDK_GetDVRWorkState(int lLoginID, IntPtr lpWorkState);

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern int NET_SDK_FindFileByName(
            int lLoginID,
            IntPtr lpFindInfo,
            IntPtr lpFileData,
            int maxFileNum,
            ref int fileNum,
            int waittime
        );

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
        public static extern int NET_SDK_GetFileByName(
            int lLoginID,
            IntPtr lpFileDataRecord,
            string sSavedFileName,
            IntPtr cbDownLoadPos,
            IntPtr dwUserData
        );

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern int NET_SDK_GetDownloadPos(int hDownloadHandle);

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern bool NET_SDK_StopGetFile(int hDownloadHandle);

        [DllImport(DllName, CallingConvention = CallingConvention.StdCall)]
        public static extern bool NET_SDK_SetSystemDateTime(int lLoginID, IntPtr lpSystemTime);
    }
}
