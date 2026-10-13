using System;

namespace NetDvrSdk
{
    public enum DvrRecordType
    {
        All = 0,
        Alarm = 1,
        Regular = 8
    }

    public class DvrDeviceInfo
    {
        public string FirmwareVersion { get; set; }
        public string SerialNumber { get; set; }
        public string OemInfo { get; set; }
    }

    public class DvrRecordFile
    {
        public int ChannelIndex { get; set; } // 0-based
        public int ChannelNumber => ChannelIndex + 1; // 1-based
        public long SizeBytes { get; set; }
        public double SizeMB => SizeBytes / (1024.0 * 1024.0);
        public string RemotePath { get; set; }
        public DateTime StartTime { get; set; }
        public DateTime EndTime { get; set; }
        public TimeSpan Duration => EndTime - StartTime;
        public string TriggerType { get; set; } // "H" = Alarm/Motion, "R" = Regular
        public byte[] RawRecordBytes { get; internal set; }

        public string GenerateCleanFileName(string extension = ".mp4")
        {
            return string.Format("ch{0:D2}_{1:yyyy-MM-dd}_{2:HH.mm.ss}-{3:HH.mm.ss}[{4}]{5}",
                ChannelNumber, StartTime, StartTime, EndTime, TriggerType, extension);
        }
    }

    public class DvrDownloadProgress
    {
        public int Percentage { get; set; }
        public long BytesDownloaded { get; set; }
        public double SpeedMBs { get; set; }
    }
}
