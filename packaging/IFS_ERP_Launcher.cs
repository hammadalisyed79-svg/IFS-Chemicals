// IFS chemicals ERP — desktop launcher
// Compile: packaging\build_launcher_exe.bat
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    private const string AppTitle = "IFS chemicals ERP";
    private const int ErpPort = 8501;

    [STAThread]
    private static void Main()
    {
        try
        {
            string root = FindErpRoot();
            if (root == null)
            {
                MessageBox.Show(
                    "Could not find IFS ERP folder (app.py / venv missing).\n" +
                    "Place IFS_ERP.exe in the ERP install folder.",
                    AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            Directory.SetCurrentDirectory(root);

            // Always use Streamlit port 8501 — never open port 80 (IIS default page).
            if (!IsErpReady(ErpPort))
            {
                if (!StartStreamlit(root, ErpPort))
                    return;
                if (!WaitForErp(ErpPort, 60000))
                {
                    MessageBox.Show(
                        "ERP started but did not become ready in time.\n" +
                        "Check the console window for errors, then open:\n" +
                        "http://127.0.0.1:8501/",
                        AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
            }

            Process.Start(new ProcessStartInfo
            {
                FileName = "http://127.0.0.1:8501/",
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static string FindErpRoot()
    {
        string exeDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
        string[] candidates = {
            exeDir,
            Path.GetFullPath(Path.Combine(exeDir, "..")),
            Path.GetFullPath(Path.Combine(exeDir, "..", "..")),
        };
        foreach (string c in candidates)
        {
            if (File.Exists(Path.Combine(c, "app.py")) &&
                File.Exists(Path.Combine(c, "venv", "Scripts", "python.exe")))
                return c;
        }
        return null;
    }

    private static bool StartStreamlit(string root, int port)
    {
        string python = Path.Combine(root, "venv", "Scripts", "python.exe");
        if (!File.Exists(python))
        {
            MessageBox.Show(
                "Python venv not found.\nRun install\\windows_install.bat first.",
                AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = string.Format(
                "-m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port {0} --browser.gatherUsageStats false",
                port),
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = false,
        };
        Process.Start(psi);
        return true;
    }

    private static bool IsPortOpen(int port)
    {
        try
        {
            using (var c = new TcpClient())
            {
                var ar = c.BeginConnect("127.0.0.1", port, null, null);
                bool ok = ar.AsyncWaitHandle.WaitOne(400);
                if (!ok) return false;
                c.EndConnect(ar);
                return true;
            }
        }
        catch
        {
            return false;
        }
    }

    private static bool IsErpReady(int port)
    {
        if (!IsPortOpen(port))
            return false;
        try
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            var req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/");
            req.Timeout = 2500;
            req.ReadWriteTimeout = 2500;
            req.Method = "GET";
            req.UserAgent = "IFS-ERP-Launcher";
            using (var resp = (HttpWebResponse)req.GetResponse())
            using (var reader = new StreamReader(resp.GetResponseStream()))
            {
                string body = reader.ReadToEnd();
                // Streamlit pages include these markers; IIS welcome page does not.
                return body.IndexOf("streamlit", StringComparison.OrdinalIgnoreCase) >= 0
                    || body.IndexOf("IFS", StringComparison.OrdinalIgnoreCase) >= 0;
            }
        }
        catch
        {
            // Port open but not HTTP ERP yet — treat as not ready.
            return false;
        }
    }

    private static bool WaitForErp(int port, int timeoutMs)
    {
        int waited = 0;
        while (waited < timeoutMs)
        {
            if (IsErpReady(port))
                return true;
            Thread.Sleep(700);
            waited += 700;
        }
        return false;
    }
}
