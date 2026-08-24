// IFS chemicals ERP — client PC launcher (opens remote server in browser)
// Does NOT start Streamlit locally — for staff PCs connecting to the ERP server.
// Compile: packaging\build_client_exe.bat
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    private const string AppTitle = "IFS chemicals ERP";
    // Public ERP server (Hetzner)
    private const string DefaultUrl = "https://erp.ifschemicals.com/";

    [STAThread]
    private static void Main()
    {
        try
        {
            string url = ReadConfiguredUrl() ?? DefaultUrl;
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "Could not open IFS chemicals ERP.\n\n" +
                "Try this address in your browser:\n" +
                DefaultUrl + "\n\n" +
                ex.Message,
                AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    /// <summary>
    /// Optional erp_url.txt next to the EXE (one line = full URL).
    /// </summary>
    private static string ReadConfiguredUrl()
    {
        try
        {
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            string cfg = Path.Combine(dir, "erp_url.txt");
            if (!File.Exists(cfg))
                return null;
            string line = File.ReadAllText(cfg).Trim();
            if (line.Length == 0)
                return null;
            if (!line.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
                !line.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                return null;
            return line;
        }
        catch
        {
            return null;
        }
    }
}
