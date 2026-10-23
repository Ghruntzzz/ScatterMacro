// A self-contained Windows entry point. Runtime files live in LocalAppData.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyVersion("0.4.2.0")]
[assembly: AssemblyFileVersion("0.4.2.0")]
[assembly: AssemblyInformationalVersion("0.4.2")]
[assembly: AssemblyProduct("ScatterMacro Launcher")]

class LauncherBootstrap
{
    const string EmbeddedVersion = "0.4.2";

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ScatterMacro", "launcher");
            Directory.CreateDirectory(root);
            string directory;
            using (Mutex mutex = new Mutex(false, "Local\\ScatterMacro.LauncherInstall"))
            {
                bool held;
                try { held = mutex.WaitOne(120000); }
                catch (AbandonedMutexException) { held = true; }
                if (!held) throw new IOException("Another launcher installation is still running.");
                try { directory = EnsureInstalled(root); }
                finally { mutex.ReleaseMutex(); }
            }
            if (Array.IndexOf(args, "--install-only") >= 0) return 0;
            Process.Start(new ProcessStartInfo(Path.Combine(directory, "ScatterLauncher.exe")) {
                WorkingDirectory = directory, UseShellExecute = false, CreateNoWindow = true
            });
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show("ScatterMacro could not open.\n\n" + error.Message, "ScatterMacro", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string EnsureInstalled(string root)
    {
        string pointer = Path.Combine(root, "current.txt");
        Version embedded = new Version(EmbeddedVersion);
        if (File.Exists(pointer))
        {
            string current = File.ReadAllText(pointer).Trim();
            Version version;
            if (Version.TryParse(current, out version) && version >= embedded && current == version.ToString())
            {
                string existing = Path.Combine(root, current);
                if (File.Exists(Path.Combine(existing, "ScatterLauncher.exe")) && File.Exists(Path.Combine(existing, "_internal", "catalog.json")))
                    return existing;
            }
        }
        string target = Path.Combine(root, EmbeddedVersion);
        string expected;
        using (StreamReader reader = new StreamReader(Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.sha256")))
            expected = reader.ReadToEnd().Trim().ToLowerInvariant();
        string receipt = Path.Combine(target, "payload.sha256");
        if (!File.Exists(receipt) || File.ReadAllText(receipt).Trim() != expected || !File.Exists(Path.Combine(target, "ScatterLauncher.exe")))
        {
            string stage = Path.Combine(root, ".install-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            try
            {
                using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
                {
                    using (SHA256 sha = SHA256.Create())
                    {
                        string actual = BitConverter.ToString(sha.ComputeHash(payload)).Replace("-", "").ToLowerInvariant();
                        if (actual != expected) throw new IOException("The embedded launcher package is damaged. Download it again.");
                    }
                    payload.Position = 0;
                    using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
                    {
                        foreach (ZipArchiveEntry entry in archive.Entries)
                        {
                            string name = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                            string output = Path.GetFullPath(Path.Combine(stage, name));
                            if (!output.StartsWith(stage + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                                throw new IOException("Unsafe launcher package path.");
                            if (String.IsNullOrEmpty(entry.Name)) Directory.CreateDirectory(output);
                            else
                            {
                                Directory.CreateDirectory(Path.GetDirectoryName(output));
                                entry.ExtractToFile(output, false);
                            }
                        }
                    }
                }
                string runtime = Path.Combine(stage, "ScatterLauncher");
                if (!File.Exists(Path.Combine(runtime, "ScatterLauncher.exe"))) throw new IOException("Incomplete launcher package.");
                File.WriteAllText(Path.Combine(runtime, "payload.sha256"), expected);
                // Never delete an active runtime; retain an existing install for recovery.
                string backup = null;
                if (Directory.Exists(target))
                {
                    backup = target + ".backup-" + Guid.NewGuid().ToString("N");
                    Directory.Move(target, backup);
                }
                try { Directory.Move(runtime, target); }
                catch
                {
                    if (backup != null && !Directory.Exists(target)) Directory.Move(backup, target);
                    throw;
                }
            }
            finally { if (Directory.Exists(stage)) Directory.Delete(stage, true); }
        }
        string temporary = pointer + "." + Guid.NewGuid().ToString("N") + ".tmp";
        File.WriteAllText(temporary, EmbeddedVersion);
        if (File.Exists(pointer)) File.Replace(temporary, pointer, null);
        else File.Move(temporary, pointer);
        return target;
    }
}
