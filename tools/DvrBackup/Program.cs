using System;
using System.Collections.Generic;
using System.IO;
using NetDvrSdk;

namespace DvrBackupTool
{
    class Program
    {
        static string ip = "192.168.1.100";
        static int port = 34567;
        static string user = "admin";
        static string pass = "";
        static int channel = 1;
        static string mode = "download";
        static string outDir = @"recordings";
        static int days = 1;
        static DateTime? startDate = null;
        static DateTime? endDate = null;
        static TimeSpan? timeAfter = null;
        static int? latestCount = null;
        static bool keepRaw = false;
        static string ffmpegPath = "ffmpeg";

        static void PrintUsage()
        {
            Console.WriteLine("==================================================");
            Console.WriteLine("       OpenXM-DVR - Hard Disk Backup Tool         ");
            Console.WriteLine("==================================================");
            Console.WriteLine("Usage: DvrBackup.exe [options]");
            Console.WriteLine("Options:");
            Console.WriteLine("  --mode <list|download>   Action mode (default: download)");
            Console.WriteLine("  --channel <1..N>         Channel number (1-based, default: 1)");
            Console.WriteLine("  --days <N>               Number of past days to query (default: 1)");
            Console.WriteLine("  --date <YYYY-MM-DD>      Process a specific single date");
            Console.WriteLine("  --start <YYYY-MM-DD>     Start date range");
            Console.WriteLine("  --end <YYYY-MM-DD>       End date range");
            Console.WriteLine("  --after <HH:mm:ss>       Only process recordings ending after this time");
            Console.WriteLine("  --latest <N>             Only process the last N recording segments");
            Console.WriteLine("  --out <directory>        Output directory (default: recordings)");
            Console.WriteLine("  --keep-raw               Keep .h264 raw stream after MP4 conversion");
            Console.WriteLine("  --ip <ip>                DVR IP address (default: 192.168.1.100)");
            Console.WriteLine("  --port <port>            DVR Port (default: 34567)");
            Console.WriteLine("  --user <user>            Username (default: admin)");
            Console.WriteLine("  --pass <pass>            Password (default: blank)");
            Console.WriteLine("  --ffmpeg <path>          Path to ffmpeg binary");
        }

        static void ParseArgs(string[] args)
        {
            for (int i = 0; i < args.Length; i++)
            {
                string arg = args[i].ToLowerInvariant();
                if (arg == "--help" || arg == "-h") { PrintUsage(); Environment.Exit(0); }
                else if (arg == "--mode" && i + 1 < args.Length) mode = args[++i].ToLowerInvariant();
                else if (arg == "--channel" && i + 1 < args.Length) channel = int.Parse(args[++i]);
                else if (arg == "--days" && i + 1 < args.Length) days = int.Parse(args[++i]);
                else if (arg == "--date" && i + 1 < args.Length)
                {
                    DateTime d = DateTime.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture);
                    startDate = d;
                    endDate = d;
                }
                else if (arg == "--start" && i + 1 < args.Length) startDate = DateTime.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture);
                else if (arg == "--end" && i + 1 < args.Length) endDate = DateTime.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture);
                else if (arg == "--after" && i + 1 < args.Length) timeAfter = TimeSpan.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture);
                else if (arg == "--latest" && i + 1 < args.Length) latestCount = int.Parse(args[++i]);
                else if (arg == "--out" && i + 1 < args.Length) outDir = args[++i];
                else if (arg == "--keep-raw") keepRaw = true;
                else if (arg == "--ip" && i + 1 < args.Length) ip = args[++i];
                else if (arg == "--port" && i + 1 < args.Length) port = int.Parse(args[++i]);
                else if (arg == "--user" && i + 1 < args.Length) user = args[++i];
                else if (arg == "--pass" && i + 1 < args.Length) pass = args[++i];
                else if (arg == "--ffmpeg" && i + 1 < args.Length) ffmpegPath = args[++i];
            }
        }

        static void Main(string[] args)
        {
            ParseArgs(args);

            if (!Directory.Exists(outDir)) Directory.CreateDirectory(outDir);

            Console.WriteLine("Connecting to DVR at {0}:{1}...", ip, port);
            using (var client = new DvrClient())
            {
                if (!client.Connect(ip, port, user, pass))
                {
                    Console.WriteLine("[ERROR] Failed to connect to DVR. Check network / credentials.");
                    return;
                }

                Console.WriteLine("[OK] Connected! Session ID: {0}", client.SessionId);

                DateTime today = DateTime.Today;
                DateTime sDate = startDate ?? today.AddDays(-(days - 1));
                DateTime eDate = endDate ?? today;

                Console.WriteLine("Scanning DVR Hard Disk from {0:yyyy-MM-dd} to {1:yyyy-MM-dd} (Channel {2})...", sDate, eDate, channel);
                var allFiles = new List<DvrRecordFile>();

                for (DateTime cur = sDate; cur <= eDate; cur = cur.AddDays(1))
                {
                    var dayFiles = client.QueryFiles(channel - 1, cur);
                    Console.WriteLine("  {0:yyyy-MM-dd}: Found {1} recordings", cur, dayFiles.Count);
                    allFiles.AddRange(dayFiles);
                }

                if (timeAfter.HasValue)
                {
                    allFiles = allFiles.FindAll(f => f.EndTime.TimeOfDay > timeAfter.Value);
                    Console.WriteLine("Filtered by --after {0}: {1} files match", timeAfter.Value, allFiles.Count);
                }

                if (latestCount.HasValue && allFiles.Count > latestCount.Value)
                {
                    allFiles = allFiles.GetRange(allFiles.Count - latestCount.Value, latestCount.Value);
                    Console.WriteLine("Filtered to latest {0} files", latestCount.Value);
                }

                if (mode == "list")
                {
                    Console.WriteLine();
                    Console.WriteLine("{0,-4} | {1,-10} | {2,-19} | {3,8} MB | {4}", "No", "Date", "Time Range", "Size", "Filename");
                    Console.WriteLine(new string('-', 85));
                    for (int i = 0; i < allFiles.Count; i++)
                    {
                        var f = allFiles[i];
                        Console.WriteLine("{0,-4} | {1:yyyy-MM-dd} | {2:HH.mm.ss}-{3:HH.mm.ss} | {4,8:F1} MB | {5}",
                            i + 1, f.StartTime, f.StartTime, f.EndTime, f.SizeMB, Path.GetFileName(f.RemotePath));
                    }
                    return;
                }

                // Download mode
                int downloaded = 0, skipped = 0, failed = 0;
                for (int i = 0; i < allFiles.Count; i++)
                {
                    var f = allFiles[i];
                    string mp4Name = f.GenerateCleanFileName(".mp4");
                    string h264Name = f.GenerateCleanFileName(".h264");
                    string targetMp4 = Path.Combine(outDir, mp4Name);
                    string targetH264 = Path.Combine(outDir, h264Name);

                    Console.WriteLine();
                    Console.WriteLine("[{0}/{1}] {2} ({3:F1} MB)", i + 1, allFiles.Count, mp4Name, f.SizeMB);

                    if (File.Exists(targetMp4) && new FileInfo(targetMp4).Length > 1024 * 1024)
                    {
                        Console.WriteLine("   -> Already downloaded and converted. Skipping.");
                        skipped++;
                        continue;
                    }

                    bool ok = client.DownloadFile(f, targetH264, prog =>
                    {
                        Console.Write("\r   Progress: {0,3}% | {1:F1} MB | Speed: {2:F2} MB/s   ",
                            prog.Percentage, prog.BytesDownloaded / (1024.0 * 1024.0), prog.SpeedMBs);
                    });

                    if (!ok)
                    {
                        Console.WriteLine("\n   [FAILED] Download failed.");
                        failed++;
                        continue;
                    }

                    Console.WriteLine("\n   Remuxing to standard MP4 with ffmpeg...");
                    bool conv = DvrClient.ConvertToMp4(targetH264, targetMp4, ffmpegPath);
                    if (conv)
                    {
                        Console.WriteLine("   [SUCCESS] Saved: {0}", mp4Name);
                        if (!keepRaw && File.Exists(targetH264))
                        {
                            try { File.Delete(targetH264); } catch { }
                        }
                        downloaded++;
                    }
                    else
                    {
                        Console.WriteLine("   [WARNING] ffmpeg conversion failed, keeping raw .h264");
                        failed++;
                    }
                }

                Console.WriteLine();
                Console.WriteLine("==================================================");
                Console.WriteLine("Backup Complete: {0} downloaded, {1} skipped, {2} failed.", downloaded, skipped, failed);
                Console.WriteLine("Saved folder: {0}", Path.GetFullPath(outDir));
                Console.WriteLine("==================================================");
            }
        }
    }
}
