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

        public bool IsConnected { get { return _loginId > 0; } }
        public int SessionId { get { return _loginId; } }

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

                        // 1. Read binary SDK_SYSTEM_TIME structs from rawRec (offsets 116 and 140)
                        try
                        {
                            if (rawRec.Length >= 164)
                            {
                                int sy = BitConverter.ToInt32(rawRec, 116);
                                int sm = BitConverter.ToInt32(rawRec, 120);
                                int sd = BitConverter.ToInt32(rawRec, 124);
                                int sh = BitConverter.ToInt32(rawRec, 128);
                                int smn = BitConverter.ToInt32(rawRec, 132);
                                int ss = BitConverter.ToInt32(rawRec, 136);

                                int ey = BitConverter.ToInt32(rawRec, 140);
                                int em = BitConverter.ToInt32(rawRec, 144);
                                int eday = BitConverter.ToInt32(rawRec, 148);
                                int eh = BitConverter.ToInt32(rawRec, 152);
                                int emn = BitConverter.ToInt32(rawRec, 156);
                                int es = BitConverter.ToInt32(rawRec, 160);

                                if (sy >= 2000 && sy <= 2099 && sm >= 1 && sm <= 12 && sd >= 1 && sd <= 31 &&
                                    sh >= 0 && sh <= 23 && smn >= 0 && smn <= 59 && ss >= 0 && ss <= 59)
                                {
                                    st = new DateTime(sy, sm, sd, sh, smn, ss);
                                }
                                if (ey >= 2000 && ey <= 2099 && em >= 1 && em <= 12 && eday >= 1 && eday <= 31 &&
                                    eh >= 0 && eh <= 23 && emn >= 0 && emn <= 59 && es >= 0 && es <= 59)
                                {
                                    ed = new DateTime(ey, em, eday, eh, emn, es);
                                }
                            }
                        }
                        catch { }

                        // 2. Regex fallback / trigger extraction from filename
                        Match m = Regex.Match(remotePath, @"(\d{2})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})(?:\[([A-Za-z0-9])\])?");
                        if (m.Success)
                        {
                            if (st == date)
                            {
                                st = new DateTime(date.Year, date.Month, date.Day,
                                    int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value), int.Parse(m.Groups[3].Value));
                            }
                            if (ed == date)
                            {
                                ed = new DateTime(date.Year, date.Month, date.Day,
                                    int.Parse(m.Groups[4].Value), int.Parse(m.Groups[5].Value), int.Parse(m.Groups[6].Value));
                            }
                            if (m.Groups[7].Success && !string.IsNullOrEmpty(m.Groups[7].Value))
                            {
                                trig = m.Groups[7].Value;
                            }
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
                long lastSize = -1;

                while ((DateTime.Now - startTime).TotalSeconds < timeoutSeconds)
                {
                    int pos = NativeMethods.NET_SDK_GetDownloadPos(hDown);
                    long currentSize = File.Exists(localRawPath) ? new FileInfo(localRawPath).Length : 0;

                    if (pos != lastPos || currentSize != lastSize)
                    {
                        lastProgressTime = DateTime.Now;
                        lastPos = pos;
                        lastSize = currentSize;
                        double elapsed = (DateTime.Now - startTime).TotalSeconds;
                        double speed = (elapsed > 0) ? (currentSize / (1024.0 * 1024.0)) / elapsed : 0;

                        if (progressCallback != null)
                        {
                            progressCallback(new DvrDownloadProgress
                            {
                                Percentage = pos,
                                BytesDownloaded = currentSize,
                                SpeedMBs = speed
                            });
                        }
                    }

                    if (pos >= 100) return true;
                    if (pos < 0) return false;

                    // Stall detection (no percentage change and no byte growth for 45s)
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
                    Arguments = string.Format(System.Globalization.CultureInfo.InvariantCulture,
                        "-y -loglevel error -nostats -r 25 -i \"{0}\" -c copy \"{1}\"", inputRawH264, outputMp4),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardError = true,
                    RedirectStandardOutput = false
                };

                using (var p = Process.Start(psi))
                {
                    string stderr = p.StandardError.ReadToEnd();
                    bool exited = p.WaitForExit(60000);
                    if (!exited)
                    {
                        try { p.Kill(); } catch { }
                        return false;
                    }
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
