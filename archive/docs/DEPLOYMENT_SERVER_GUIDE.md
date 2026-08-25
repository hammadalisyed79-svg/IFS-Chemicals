# IFS Industrial ERP — Server Deployment Guide

**Version:** V15.0  
**Server IP:** `138.201.139.157`  
**Goal:** HTTPS-only external access via Nginx reverse proxy. **Never expose Streamlit ports directly.**

---

## Architecture

```
Internet → Nginx (443 HTTPS) → 127.0.0.1:8501 (internal ERP app.py)
                             → 127.0.0.1:8502 (distributor portal_app.py)
SQLite ifs_erp.db (not web-accessible)
```

| Service | Bind | Public URL |
|---------|------|------------|
| Internal ERP | `127.0.0.1:8501` | `https://138.201.139.157/` |
| Distributor portal | `127.0.0.1:8502` | `https://138.201.139.157/portal` |

---

## 1. Prepare server (Linux)

```bash
sudo apt update && sudo apt install -y python3-venv nginx certbot python3-certbot-nginx ufw
```

Copy project to `/opt/ifs-erp` and create venv:

```bash
cd /opt/ifs-erp
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

---

## 2. Streamlit services (localhost only)

Use `SYSTEMD_SERVICE_SAMPLE.service` for internal ERP and duplicate for portal on port 8502:

```bash
# Internal ERP
streamlit run app.py --server.port=8501 --server.address=127.0.0.1

# Distributor portal
streamlit run portal_app.py --server.port=8502 --server.address=127.0.0.1 --server.baseUrlPath=portal
```

Enable systemd units:

```bash
sudo cp SYSTEMD_SERVICE_SAMPLE.service /etc/systemd/system/ifs-erp.service
sudo systemctl daemon-reload
sudo systemctl enable --now ifs-erp
```

---

## 3. Nginx

Copy `NGINX_CONFIG_SAMPLE.conf` to `/etc/nginx/sites-available/ifs-erp` and enable:

```bash
sudo ln -s /etc/nginx/sites-available/ifs-erp /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 4. SSL

Follow `SSL_SETUP_GUIDE.md`, then set in ERP **System Settings**:

- `ssl_configured` = `1`

---

## 5. Firewall

Follow `FIREWALL_SECURITY_GUIDE.md`:

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

**Do not** open ports 8501 or 8502.

---

## 6. Database protection

- Keep `ifs_erp.db` outside the web root.
- Nginx must not serve `.db`, `.sql`, or backup files.
- Restrict filesystem permissions: `chmod 600 ifs_erp.db` (app user only).

---

## 7. Post-deploy checks

1. `https://138.201.139.157/` loads login (not `http://138.201.139.157:8501`).
2. Distributor login at `https://138.201.139.157/portal`.
3. ERP Health Check → V15 portal/security checks pass.
4. Run `python tests/test_portal_security.py`.

---

## Windows Server note

Use IIS ARR or Nginx for Windows with the same localhost binding pattern. Streamlit `address = 127.0.0.1` in `.streamlit/config.toml`.
