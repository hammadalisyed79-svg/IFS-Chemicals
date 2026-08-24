# IFS chemicals ERP — client access

## Browser (any PC / phone)

Open:

**https://erp.ifschemicals.com/**

Login with your username (e.g. shabab, usman, mudassar, hammad).

## Windows desktop app (download)

1. Sign in to the ERP.
2. Open **Overview → Download App**.
3. Click **Download IFS_Chemicals_ERP.exe**.
4. On the client PC, double-click the EXE — it opens **https://erp.ifschemicals.com/**.

Or copy the whole folder from the server:

`C:\MY ERPS\client_dist\`

Contents:

| File | Purpose |
|------|---------|
| `IFS_Chemicals_ERP.exe` | Shortcut app |
| `erp_url.txt` | Target URL (`https://erp.ifschemicals.com/`) |
| `IFS_Chemicals_ERP.url` | Browser shortcut |
| `README.txt` | Instructions |

Rebuild on the server anytime:

```bat
packaging\build_client_exe.bat
```

## Server note

ERP must be running with HTTPS proxy (`IFS_ERP_Final_Run.bat` or `restart_https.bat`).
The public site is **https://erp.ifschemicals.com/** (not the raw IP).
