using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

namespace NetDvrSdk
{
    /// <summary>
    /// High-level client for interacting with Port 34567 CCTV DVRs.
    /// </summary>
    public class DvrClient : IDisposable
    {
        private int _loginId = 0;
        private bool _disposed = false;
        private static bool _initialized = false;
        private static readonly object _initLock = new object();

        public bool IsConnected => _loginId > 0;
        public int SessionId => _loginId;

        public DvrClient()
        {
            lock (_initLock)
            {
                if (!_initialized)
                {
                    NativeMethods.NET_SDK_Init(IntPtr.Zero, IntPtr.Zero);
                    _initialized = true;
                }
            }
        }

        /// <summary>
        /// Authenticates and establishes a session with the DVR.
        /// </summary>
        public bool Connect(string ip, int port, string username, string password)
        {
            if (IsConnected) Disconnect();

            IntPtr pDevInfo = Marshal.AllocHGlobal(4096);
            IntPtr pError = Marshal.AllocHGlobal(16);

            try
            {
                int lLogin = NativeMethods.NET_SDK_Login(ip, port, username, password, pDevInfo, 0, pError, 0, 0);
                if (lLogin > 0)
                {
                    _loginId = lLogin;
                    return true;
                }
                return false;
            }
            finally
            {
                Marshal.FreeHGlobal(pDevInfo);
                Marshal.FreeHGlobal(pError);
            }
        }

        /// <summary>
        /// Disconnects from the DVR.
        /// </summary>
        public void Disconnect()
        {
            if (_loginId > 0)
            {
                NativeMethods.NET_SDK_Logout(_loginId);
                _loginId = 0;
            }
        }

        /// <summary>
        /// Queries the hard disk catalogue for recorded files for a given channel and date.
        /// </summary>
        public List<DvrRecordFile> QueryFiles(int channelIndex, DateTime date, DvrRecordType recordType = DvrRecordType.All)
        {
            EnsureConnected();
            var list = new List<DvrRecordFile>();

            const int maxFiles = 300;
            const int recordSize = 180;
            IntPtr pFileData = Marshal.AllocHGlobal(recordSize * maxFiles);
            for (int i = 0; i < recordSize * maxFiles; i++) Marshal.WriteByte(pFileData, i, 0);

            // 60-byte find struct
            byte[] findBytes = new byte[64];
            Buffer.BlockCopy(BitConverter.GetBytes(channelIndex), 0, findBytes, 0, 4);
            Buffer.BlockCopy(BitConverter.GetBytes((int)recordType), 0, findBytes, 4, 4);

            int[] startArr = { date.Year, date.Month, date.Day, 0, 0, 0 };
            for (int k = 0; k < 6; k++) Buffer.BlockCopy(BitConverter.GetBytes(startArr[k]), 0, findBytes, 8 + k * 4, 4);

            int[] endArr = { date.Year, date.Month, date.Day, 23, 59, 59 };
            for (int k = 0; k < 6; k++) Buffer.BlockCopy(BitConverter.GetBytes(endArr[k]), 0, findBytes, 32 + k * 4, 4);

            IntPtr pFind = Marshal.AllocHGlobal(findBytes.Length);
            Marshal.Copy(findBytes, 0, pFind, findBytes.Length);

            int count = 0;
            try
            {
                int ret = NativeMethods.NET_SDK_FindFileByName(_loginId, pFind, pFileData, maxFiles, ref count, 5000);
                if (ret > 0 && count > 0)
                {
                    for (int i = 0; i < count; i++)
                    {
                        byte[] rawRec = new byte[recordSize];
                        Marshal.Copy(new IntPtr(pFileData.ToInt64() + i * recordSize), rawRec, 0, recordSize);

                        int ch = BitConverter.ToInt32(rawRec, 0);
                        int sizeKb = BitConverter.ToInt32(rawRec, 4);

                        string remotePath = "";
                        for (int j = 8; j < 116; j++)
                        {
                            if (rawRec[j] == 0) break;
                            remotePath += (char)rawRec[j];
                        }

                        DateTime st = date;
                        DateTime ed = date;
                        string trig = "R";

                        Match m = Regex.Match(remotePath, @"(\d{2})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})\[([A-Z])\]");
                        if (m.Success)
                        {
                            st = new DateTime(date.Year, date.Month, date.Day,
                                int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value), int.Parse(m.Groups[3].Value));
                            ed = new DateTime(date.Year, date.Month, date.Day,
                                int.Parse(m.Groups[4].Value), int.Parse(m.Groups[5].Value), int.Parse(m.Groups[6].Value));
                            trig = m.Groups[7].Value;
                        }

                        list.Add(new DvrRecordFile
                        {
                            ChannelIndex = ch,
                            SizeBytes = (long)sizeKb * 1024L,
                            RemotePath = remotePath,
                            StartTime = st,
                            EndTime = ed,
                            TriggerType = trig,
                            RawRecordBytes = rawRec
                        });
                    }
                }
            }
            finally
            {
                Marshal.FreeHGlobal(pFind);
                Marshal.FreeHGlobal(pFileData);
            }

            return list;
        }

        /// <summary>
        /// Downloads a recorded file directly from the DVR internal storage to local disk.
        /// </summary>
        public bool DownloadFile(DvrRecordFile file, string localRawPath, Action<DvrDownloadProgress> progressCallback = null, int timeoutSeconds = 600)
        {
            EnsureConnected();
            if (File.Exists(localRawPath))
            {
                try { File.Delete(localRawPath); } catch { }
            }

            IntPtr pRec = Marshal.AllocHGlobal(file.RawRecordBytes.Length);
            Marshal.Copy(file.RawRecordBytes, 0, pRec, file.RawRecordBytes.Length);

            int hDown = 0;
            try
            {
                hDown = NativeMethods.NET_SDK_GetFileByName(_loginId, pRec, localRawPath, IntPtr.Zero, IntPtr.Zero);
            }
            finally
            {
                Marshal.FreeHGlobal(pRec);
            }

            if (hDown <= 0) return false;

            try
            {
                DateTime startTime = DateTime.Now;
                DateTime lastProgressTime = DateTime.Now;
                int lastPos = -1;

                while ((DateTime.Now - startTime).TotalSeconds < timeoutSeconds)
                {
                    int pos = NativeMethods.NET_SDK_GetDownloadPos(hDown);
                    long currentSize = File.Exists(localRawPath) ? new FileInfo(localRawPath).Length : 0;

                    if (pos != lastPos)
                    {
                        lastProgressTime = DateTime.Now;
                        lastPos = pos;
                        double elapsed = (DateTime.Now - startTime).TotalSeconds;
                        double speed = (elapsed > 0) ? (currentSize / (1024.0 * 1024.0)) / elapsed : 0;

                        progressCallback?.Invoke(new DvrDownloadProgress
                        {
                            Percentage = pos,
                            BytesDownloaded = currentSize,
                            SpeedMBs = speed
                        });
                    }

                    if (pos >= 100) return true;
                    if (pos < 0) return false;

                    // Stall detection (no progress for 45s)
                    if ((DateTime.Now - lastProgressTime).TotalSeconds > 45) return false;

                    Thread.Sleep(300);
                }
                return false;
            }
            finally
            {
                NativeMethods.NET_SDK_StopGetFile(hDown);
            }
        }

        /// <summary>
        /// Losslessly remuxes raw H.264 elementary streams into standard MP4 containers using ffmpeg.
        /// </summary>
        public static bool ConvertToMp4(string inputRawH264, string outputMp4, string ffmpegPath = "ffmpeg")
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = ffmpegPath,
                    Arguments = string.Format("-y -r 25 -i \"{0}\" -c copy \"{1}\"", inputRawH264, outputMp4),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardError = true,
                    RedirectStandardOutput = true
                };

                using (var p = Process.Start(psi))
                {
                    p.WaitForExit(60000);
                    return p.ExitCode == 0 && File.Exists(outputMp4) && new FileInfo(outputMp4).Length > 1024;
                }
            }
            catch
            {
                return false;
            }
        }

        private void EnsureConnected()
        {
            if (!IsConnected) throw new InvalidOperationException("Not connected to DVR. Call Connect() first.");
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                Disconnect();
                _disposed = true;
            }
            GC.SuppressFinalize(this);
        }
    }
}
