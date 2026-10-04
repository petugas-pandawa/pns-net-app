#!/usr/bin/env python3
# ============================================================
# bridge.py — CIOT Bridge Server v2.0
# PT. Pandawa Nusantara Solusindo
#
# Letakkan di: ~/ciot-modem-tool/bridge.py
# Jalankan   : python3 bridge.py
# Buka browser: http://127.0.0.1:8088
#
# Perbedaan dari web_ui.py lama:
# - Arsitektur driver per merek modem (folder modem/)
# - Endpoint /status untuk cek dari web app PNS.NET
# - CORS header aktif (siap terima request dari GitHub Pages)
# - UI darurat tetap ada jika web app PNS.NET tidak bisa diakses
# ============================================================

import io
import json
import contextlib
import subprocess
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
from modem import get_driver, list_drivers, ManualModem
from modem.base import empty_summary

PORT = 8088

# ── Session per host ──────────────────────────────────────────
_sessions: dict = {}

def get_session(host: str, merek: str = "ciot"):
    if host not in _sessions:
        _sessions[host] = get_driver(merek, host)
    return _sessions[host]

def clear_session(host: str):
    if host in _sessions:
        del _sessions[host]

# ── PNS.NET API URL ───────────────────────────────────────────
PNSNET_API_URL = getattr(
    config, 'PNSNET_API_URL',
    'https://script.google.com/macros/s/'
    'AKfycbyQZHQH5WLDyAiGOxz7NEbbhGXMB4fP4ANkJTN9qJjNjv4Y2xQmZRqXR1tPwvEgTnP1'
    '/exec'
)

# ── SVG logo perusahaan ───────────────────────────────────────
LOGO_SVG = '''<svg width="38" height="38" viewBox="0 0 1200 1200" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="225" cy="788" rx="120" ry="121" fill="#E30613"/>
  <rect x="362" y="598" width="127" height="308" rx="16.5" fill="#E30613"/>
  <rect x="517" y="525" width="118" height="381" rx="15.34" fill="#E30613"/>
  <rect x="661" y="454" width="124" height="452" rx="16.12" fill="#1A4FBF"/>
  <rect x="809" y="377" width="128" height="529" rx="16.64" fill="#1A4FBF"/>
  <rect x="963" y="280" width="130" height="626" rx="16.9" fill="#FF7A00"/>
</svg>'''

# ── Action handler ────────────────────────────────────────────
def handle(payload: dict) -> tuple:
    action = payload.get("action", "")
    host   = payload.get("host", getattr(config, "HOST", "192.168.1.1")).strip()
    merek  = payload.get("merek", "ciot").strip().lower()

    if host in _sessions and \
       type(_sessions[host]).__name__.lower().replace("modem","") not in (merek, merek.replace(" ","")):
        clear_session(host)

    modem = get_session(host, merek)
    log   = io.StringIO()

    def run(fn, *a, **kw):
        with contextlib.redirect_stdout(log):
            try:    return fn(*a, **kw)
            except Exception as e:
                print(f"[ERROR] {e}")
                return False

    # ── CEK KONEKSI ───────────────────────────────────────────
    if action == "check":
        ok = run(modem.check_connection)
        print(f"[{'OK' if ok else 'GAGAL'}] {'Modem terjangkau di ' + host if ok else 'Tidak bisa menjangkau ' + host}", file=log)
        return log.getvalue(), bool(ok), {}

    # ── LOGIN ─────────────────────────────────────────────────
    elif action == "login":
        user = payload.get("username", getattr(config, "LOGIN_USERNAME", "admin"))
        pw   = payload.get("password", getattr(config, "LOGIN_PASSWORD", ""))
        ok   = run(modem.login, user, pw)
        print(f"[{'OK' if ok else 'GAGAL'}] {'Login berhasil' if ok else 'Login ditolak — cek username/password'}", file=log)
        return log.getvalue(), bool(ok), {"logged_in": modem.logged_in}

    # ── SET WiFi ──────────────────────────────────────────────
    elif action == "apply_wifi":
        if not modem.logged_in:
            return "[GAGAL] Belum login.", False, {}
        ssid = payload.get("new_essid", "").strip() or None
        pw   = payload.get("new_wifi_pass", "").strip() or None
        try:   mc = int(payload.get("new_max_client", 32))
        except: mc = 32
        ok = run(modem.set_wifi, ssid, pw, mc)
        return log.getvalue(), bool(ok), {}

    # ── SET WAN ───────────────────────────────────────────────
    elif action == "apply_wan":
        if not modem.logged_in:
            return "[GAGAL] Belum login.", False, {}
        ok = run(modem.set_wan,
            payload.get("wan_username", "").strip(),
            payload.get("wan_password", "").strip(),
            payload.get("wan_vlan_id", "10").strip(),
            payload.get("wan_connection_name", "INTERNET").strip())
        return log.getvalue(), bool(ok), {}

    # ── SET RADIO ─────────────────────────────────────────────
    elif action == "apply_radio":
        if not modem.logged_in:
            return "[GAGAL] Belum login.", False, {}
        ok = run(modem.set_radio,
            channel  =payload.get("radio_channel","").strip() or None,
            bandwidth=payload.get("radio_bandwidth","").strip() or None)
        return log.getvalue(), bool(ok), {}

    # ── SET ADMIN PASSWORD ────────────────────────────────────
    elif action == "apply_admin":
        if not modem.logged_in:
            return "[GAGAL] Belum login.", False, {}
        val = payload.get("new_admin_pass", "").strip()
        if not val:
            return "Password baru kosong.", None, {}
        ok = run(modem.set_admin_password, val)
        return log.getvalue(), bool(ok), {}

    # ── FULL SETUP ────────────────────────────────────────────
    elif action == "full_setup":
        if not modem.logged_in:
            user = payload.get("username", getattr(config, "LOGIN_USERNAME", "admin"))
            pw   = payload.get("password", getattr(config, "LOGIN_PASSWORD", ""))
            if not run(modem.login, user, pw):
                return "[GAGAL] Login gagal. Full setup dibatalkan.", False, {}
        try:   mc = int(payload.get("new_max_client","32")) if payload.get("new_max_client") else None
        except: mc = None
        with contextlib.redirect_stdout(log):
            results = modem.full_setup(
                ssid          =payload.get("new_essid","").strip() or None,
                wifi_password =payload.get("new_wifi_pass","").strip() or None,
                max_client    =mc,
                wan_username  =payload.get("wan_username","").strip() or None,
                wan_password  =payload.get("wan_password","").strip() or None,
                vlan_id       =payload.get("wan_vlan_id","10").strip() or None,
                admin_password=payload.get("new_admin_pass","").strip() or None,
                channel       =payload.get("radio_channel","").strip() or None,
                bandwidth     =payload.get("radio_bandwidth","").strip() or None,
            )
        ok_all = all(v for v in results.values() if v is not None)
        print(f"Hasil: WiFi={results['wifi']} | WAN={results['wan']} "
              f"| Radio={results['radio']} | Admin={results['admin']}", file=log)
        return log.getvalue(), ok_all, {"results": results}

    # ── RINGKASAN ─────────────────────────────────────────────
    elif action == "summary":
        if not modem.logged_in:
            return "[GAGAL] Belum login.", False, {}
        with contextlib.redirect_stdout(log):
            summary = modem.get_summary()
        return log.getvalue(), True, {"summary": summary}

    # ── BAGIKAN KE PELANGGAN ──────────────────────────────────
    elif action == "customer_share":
        if not modem.logged_in:
            return "[GAGAL] Belum login.", False, {}
        with contextlib.redirect_stdout(log):
            summary = modem.get_summary()
        ssid = summary.get("ssid_wifi", "(tidak ditemukan)")
        pw   = summary.get("wifi_password_session", "")
        text = (f"WiFi Anda:\n📶 Nama WiFi : {ssid}\n"
                f"🔑 Password  : {pw if pw else '(catat saat setting)'}\n\n"
                f"Terima kasih telah berlangganan PNS.NET 🙏")
        return text, True, {"share_text": text}

    # ── KIRIM KE PNS.NET ──────────────────────────────────────
    elif action == "kirim_pnsnet":
        token    = payload.get("pnsnet_token", "").strip()
        log_only = payload.get("log_only", False)
        ket      = payload.get("keterangan", "").strip()
        if not token:
            return "[GAGAL] Token PNS.NET kosong.", False, {}
        if not modem.logged_in:
            return "[GAGAL] Belum login ke modem.", False, {}
        print("Mengambil ringkasan modem...", file=log)
        with contextlib.redirect_stdout(log):
            summary = modem.get_summary()
        if not summary.get("serial_number") and not summary.get("wan_username"):
            return log.getvalue() + "\n[GAGAL] Data modem kosong.", False, {}
        action_name = "ciot_log_only" if log_only else "ciot_kirim_ringkasan"
        post_data = {
            "action": action_name, "token": token,
            "payload": {
                "serial_number"       : summary.get("serial_number", ""),
                "mac_address"         : summary.get("mac_address", ""),
                "ip_address"          : summary.get("ip_address", ""),
                "ssid_wifi"           : summary.get("ssid_wifi", ""),
                "max_client"          : summary.get("max_client", ""),
                "wan_username"        : summary.get("wan_username", ""),
                "pon_rx_power"        : summary.get("pon_rx_power", ""),
                "wan_type"            : summary.get("wan_type", "PPPoE"),
                "wan_connection_name" : summary.get("wan_connection_name", ""),
                "firmware_info"       : summary.get("firmware_info", ""),
                "merek"               : summary.get("merek", ""),
                "model"               : summary.get("model", ""),
                "keterangan"          : ket,
            }
        }
        try:
            req = urllib.request.Request(
                PNSNET_API_URL,
                data=json.dumps(post_data).encode(),
                headers={"Content-Type": "text/plain"}, method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode())
            if result.get("ok"):
                d      = result.get("data", {})
                linked = d.get("linked", False)
                nama   = d.get("pelanggan", "")
                msg = ("[OK] Log dicatat." if log_only else
                       f"[OK] Tersimpan — terhubung ke pelanggan: {nama}" if linked else
                       "[OK] Tersimpan (WAN username belum terdaftar sebagai pelanggan aktif)")
                print(msg, file=log)
                return log.getvalue(), True, {"linked": linked, "pelanggan": nama, **d}
            else:
                print(f"[GAGAL] PNS.NET: {result.get('error','unknown')}", file=log)
                return log.getvalue(), False, {}
        except urllib.error.URLError as e:
            print(f"[GAGAL] Koneksi PNS.NET: {e.reason}", file=log)
            return log.getvalue(), False, {}
        except Exception as e:
            print(f"[GAGAL] {e}", file=log)
            return log.getvalue(), False, {}

    # ── LIST DRIVER ───────────────────────────────────────────
    elif action == "list_drivers":
        drivers = list_drivers()
        return f"Driver tersedia: {drivers}", True, {"drivers": drivers}

    # ── INPUT MANUAL (modem tidak dikenal) ────────────────────
    elif action == "manual_input":
        if not isinstance(modem, ManualModem):
            clear_session(host)
            _sessions[host] = get_driver("manual", host)
            modem = _sessions[host]
        modem.set_manual_data(**{
            k: v for k, v in payload.items()
            if k not in ("action", "host", "merek")
        })
        return "[OK] Data manual disimpan.", True, {"summary": modem.get_summary()}

    else:
        return f"[GAGAL] Action tidak dikenal: {action}", False, {}


# ── HTML UI darurat ───────────────────────────────────────────
BRIDGE_HTML = f"""<!DOCTYPE html>
<html lang="id" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CIOT Bridge — PNS.NET</title>
<style>
:root{{--bg:#0f1420;--card:#161d2e;--card2:#1c2439;
  --accent:#ff8c42;--ok:#34c77b;--err:#ff5c5c;--info:#4f8cff;
  --text:#e6e9f2;--dim:#8a92a8;--border:#26304a}}
html[data-theme=light]{{--bg:#f4f6fb;--card:#fff;--card2:#eef1f8;
  --accent:#e06a1a;--ok:#1f9d5c;--err:#e0453f;--info:#2f6fed;
  --text:#14192b;--dim:#5b6478;--border:#dde2ee}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);
  font-family:system-ui,sans-serif;font-size:14px}}
.header{{background:var(--card);border-bottom:1px solid var(--border);
  padding:10px 16px;display:flex;align-items:center;gap:10px;
  position:sticky;top:0;z-index:10}}
.brand{{flex:1;min-width:0}}
.brand-name{{font-size:14px;font-weight:700;color:var(--accent);line-height:1.2}}
.brand-sub{{font-size:10px;color:var(--dim)}}
.chip{{font-size:10px;padding:3px 9px;border-radius:10px;
  background:var(--border);color:var(--dim);white-space:nowrap}}
.chip.on{{background:rgba(52,199,123,.15);color:var(--ok)}}
.btn-theme{{background:var(--card2);border:1px solid var(--border);
  border-radius:6px;padding:5px 9px;cursor:pointer;font-size:14px;color:var(--dim)}}
.main{{padding:14px;display:flex;flex-direction:column;gap:12px;max-width:600px;margin:0 auto}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px}}
.card-title{{font-size:11px;font-weight:700;color:var(--dim);
  letter-spacing:.06em;text-transform:uppercase;margin-bottom:10px}}
label{{font-size:12px;color:var(--dim);display:block;margin-bottom:3px}}
input,select{{width:100%;padding:8px 10px;border-radius:8px;
  border:1px solid var(--border);background:var(--card2);
  color:var(--text);font-size:13px;margin-bottom:10px;outline:none}}
input:focus,select:focus{{border-color:var(--accent)}}
.row{{display:flex;gap:8px}}
.row button{{flex:1}}
button{{padding:10px;border-radius:8px;border:none;font-size:13px;
  font-weight:700;cursor:pointer;background:var(--accent);color:#fff;
  transition:filter .15s}}
button:hover{{filter:brightness(1.1)}}
button.sec{{background:var(--card2);color:var(--dim);border:1px solid var(--border)}}
.log{{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:10px;font-family:monospace;font-size:11px;max-height:180px;
  overflow-y:auto;white-space:pre-wrap;color:var(--dim);line-height:1.6}}
.log.ok{{color:var(--ok)}}.log.err{{color:var(--err)}}
.mini{{font-size:11px;color:var(--dim);margin-top:6px}}
hr{{border:none;border-top:1px solid var(--border);margin:10px 0}}
</style>
</head>
<body>
<header class="header">
  {LOGO_SVG}
  <div class="brand">
    <div class="brand-name">CIOT Bridge</div>
    <div class="brand-sub">PT. Pandawa Nusantara Solusindo · :8088</div>
  </div>
  <span class="chip" id="chip">● Belum login</span>
  <button class="btn-theme" onclick="toggleTheme()">🌙</button>
</header>

<div class="main">

  <div class="card">
    <div class="card-title">Koneksi Modem</div>
    <label>Merek</label>
    <select id="merek">
      <option value="ciot">CIOT GM220-S XPON</option>
      <option value="manual">Manual (modem lain)</option>
    </select>
    <label>Host / IP Modem</label>
    <input id="host" value="192.168.1.1">
    <label>Username</label>
    <input id="user" value="admin">
    <label>Password Admin</label>
    <input id="pass" type="password" placeholder="Password modem">
    <div class="row">
      <button class="sec" onclick="api('check')">🔍 Cek Koneksi</button>
      <button onclick="api('login')">🔑 Login</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Setting WiFi</div>
    <label>SSID / Nama WiFi</label>
    <input id="ssid" placeholder="Nama WiFi baru">
    <label>Password WiFi</label>
    <input id="wpass" type="password" placeholder="Password baru">
    <label>Max Client</label>
    <input id="mc" value="32" type="number">
    <div class="row">
      <button onclick="api('apply_wifi')">📶 Set WiFi</button>
      <button class="sec" onclick="api('summary')">📊 Ringkasan</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">WAN / PPPoE</div>
    <label>Username PPPoE</label>
    <input id="wuser" placeholder="username@server">
    <label>Password PPPoE</label>
    <input id="wpasswd" type="password">
    <label>VLAN ID</label>
    <input id="vlan" value="10">
    <button onclick="api('apply_wan')">🌐 Set WAN</button>
  </div>

  <div class="card">
    <div class="card-title">Kirim ke Database PNS.NET</div>
    <label>Token PNS.NET</label>
    <input id="ptoken" type="password" placeholder="Token dari login web app PNS.NET...">
    <label>Keterangan</label>
    <input id="pket" placeholder="Pemasangan baru / pengecekan rutin...">
    <div class="row">
      <button onclick="kirim(false)">🚀 Kirim & Update</button>
      <button class="sec" onclick="kirim(true)">📝 Log Saja</button>
    </div>
    <div id="pstatus" class="mini"></div>
  </div>

  <div class="card">
    <div class="card-title">Log Aktivitas</div>
    <div class="log" id="logBox">Menunggu aksi...</div>
  </div>

</div>

<script>
const v = id => document.getElementById(id).value.trim();

function toggleTheme(){{
  const el = document.documentElement;
  el.dataset.theme = el.dataset.theme === 'dark' ? 'light' : 'dark';
}}

function setChip(on){{
  const c = document.getElementById('chip');
  c.textContent = on ? '● Login' : '● Belum login';
  c.className = 'chip' + (on ? ' on' : '');
}}

function appendLog(text, ok){{
  const el = document.getElementById('logBox');
  el.textContent = text || '';
  el.className = 'log' + (ok === true ? ' ok' : ok === false ? ' err' : '');
  el.scrollTop = el.scrollHeight;
}}

async function api(action, extra={{}}){{
  appendLog('⟳ ' + action + '...', null);
  try{{
    const res = await fetch('/api', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        action,
        host: v('host'), merek: v('merek'),
        username: v('user'), password: v('pass'),
        new_essid: v('ssid'), new_wifi_pass: v('wpass'),
        new_max_client: v('mc'),
        wan_username: v('wuser'), wan_password: v('wpasswd'),
        wan_vlan_id: v('vlan'),
        ...extra
      }})
    }});
    const data = await res.json();
    appendLog(data.log || (data.ok ? '[OK]' : '[GAGAL]'), data.ok);
    if (data.logged_in !== undefined) setChip(data.logged_in);
    if (data.summary) showSummary(data.summary);
  }} catch(e){{
    appendLog('[GAGAL] Server tidak bisa dihubungi: ' + e.message, false);
  }}
}}

async function kirim(logOnly){{
  const token = v('ptoken');
  const st = document.getElementById('pstatus');
  if (!token){{ st.style.color='var(--err)'; st.textContent='❌ Isi token PNS.NET dulu'; return; }}
  st.style.color='var(--dim)'; st.textContent='⟳ Mengirim ke PNS.NET...';
  try{{
    const res = await fetch('/api', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        action:'kirim_pnsnet', host:v('host'), merek:v('merek'),
        pnsnet_token:token, keterangan:v('pket'), log_only:logOnly
      }})
    }});
    const data = await res.json();
    appendLog(data.log || '', data.ok);
    st.style.color = data.ok ? 'var(--ok)' : 'var(--err)';
    st.textContent = data.ok
      ? (logOnly ? '✅ Log dicatat' : '✅ Berhasil dikirim ke PNS.NET')
      : ('❌ ' + (data.log || 'Gagal'));
  }} catch(e){{
    st.style.color='var(--err)'; st.textContent='❌ ' + e.message;
  }}
}}

function showSummary(s){{
  appendLog([
    '=== RINGKASAN MODEM ===',
    'Merek/Model : ' + s.merek + ' ' + s.model,
    'Serial No.  : ' + (s.serial_number||'-'),
    'MAC Address : ' + (s.mac_address||'-'),
    'IP Address  : ' + (s.ip_address||'-'),
    'SSID WiFi   : ' + (s.ssid_wifi||'-'),
    'Max Client  : ' + (s.max_client||'-'),
    'WAN Username: ' + (s.wan_username||'-'),
    'OPM Sinyal  : ' + (s.pon_rx_power||'-'),
    'Firmware    : ' + (s.firmware_info||'-'),
  ].join('\\n'), true);
}}
</script>
</body>
</html>"""


# ── HTTP Handler ──────────────────────────────────────────────
class BridgeHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type",  "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type",  "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST,GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._html(BRIDGE_HTML)
        elif self.path == "/status":
            self._json({
                "ok"     : True,
                "bridge" : "CIOT Bridge PNS.NET",
                "version": "2.0",
                "drivers": list_drivers(),
                "port"   : PORT,
            })
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path not in ("/api", "/api/action"):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except Exception:
            self._json({"ok": False, "log": "Payload tidak valid"}, 400); return

        log_text, ok, extra = handle(payload)
        host = payload.get("host", getattr(config, "HOST", "192.168.1.1"))
        self._json({
            "ok"       : bool(ok) if ok is not None else None,
            "log"      : log_text,
            "logged_in": _sessions.get(host, type("", (), {"logged_in": False})()).logged_in,
            **extra,
        })


def main():
    server = HTTPServer(("127.0.0.1", PORT), BridgeHandler)
    print(f"\n{'='*52}")
    print(f"  CIOT Bridge v2.0 — PT. Pandawa Nusantara Solusindo")
    print(f"  UI darurat : http://127.0.0.1:{PORT}")
    print(f"  Status     : http://127.0.0.1:{PORT}/status")
    print(f"  Driver     : {list_drivers()}")
    print(f"{'='*52}\n")
    try:
        subprocess.run(
            ["termux-open-url", f"http://127.0.0.1:{PORT}"],
            timeout=5, check=False, capture_output=True)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[✓] Bridge dihentikan.")
        server.server_close()


if __name__ == "__main__":
    main()
