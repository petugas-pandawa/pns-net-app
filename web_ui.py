#!/usr/bin/env python3
# ============================================================
# CIOT MODEM SETUP — WEB UI LOKAL
# ============================================================
# Jalankan: python3 web_ui.py
# Lalu buka browser HP ke: http://127.0.0.1:8088
#
# Ini BUKAN server publik — sengaja di-bind ke 127.0.0.1 saja
# (localhost), jadi TIDAK bisa diakses dari perangkat lain di
# jaringan modem/pelanggan. Hanya bisa dibuka dari HP yang sama
# yang menjalankan Termux ini.
#
# Backend murni Python standard library (http.server), tidak ada
# dependency tambahan. Logika modem 100% reuse dari ciot_setup.py
# — file ini hanya lapisan tampilan..
# ============================================================

import io
import json
import contextlib
import subprocess
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
import ciot_setup as core

# URL Apps Script API PNS.NET
PNSNET_API_URL = getattr(
    config, 'PNSNET_API_URL',
    'https://script.google.com/macros/s/'
    'AKfycbyQZHQH5WLDyAiGOxz7NEbbhGXMB4fP4ANkJTN9qJjNjv4Y2xQmZRqXR1tPwvEgTnP1'
    '/exec'
)

PORT = 8088


# ------------------------------------------------------------
# HTML/CSS/JS — satu halaman, gaya app sederhana & rapi
# ------------------------------------------------------------
PAGE_HTML = """<!DOCTYPE html>
<html lang="id" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIOT Modem Setup — PT. Pandawa Nusantara Solusindo</title>
<style>
  :root {
    --bg: #0f1420; --card: #161d2e; --card-2: #1c2439;
    --accent: #4f8cff; --accent-2: #34c77b; --danger: #ff5c5c;
    --text: #e6e9f2; --text-dim: #8a92a8; --border: #26304a;
  }
  html[data-theme="light"] {
    --bg: #f4f6fb; --card: #ffffff; --card-2: #eef1f8;
    --accent: #2f6fed; --accent-2: #1f9d5c; --danger: #e0453f;
    --text: #14192b; --text-dim: #5b6478; --border: #dde2ee;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, Roboto, "Segoe UI", sans-serif;
    padding-bottom: 40px;
  }

  /* ---------- HEADER ---------- */
  header {
    position: sticky; top: 0; z-index: 20; background: var(--bg);
    border-bottom: 1px solid var(--border);
    padding: 12px 16px 0;
  }
  .header-top {
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 10px;
  }
  .logo-area { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .logo-area svg { flex-shrink: 0; }
  .logo-text {
    font-size: 11px; font-weight: 700; line-height: 1.2;
    color: var(--text); max-width: 120px;
  }
  .title-area { text-align: right; }
  .title-area h1 { font-size: 16px; margin: 0 0 2px; }
  .title-area .sub { font-size: 11px; color: var(--text-dim); }
  .status-badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; margin-top: 4px;
    background: var(--card-2); color: var(--text-dim);
  }
  .status-badge.on { background: rgba(52,199,123,0.15); color: var(--accent-2); }

  .host-bar {
    display: flex; justify-content: center; align-items: center;
    gap: 6px; padding: 8px 0 2px; flex-wrap: wrap;
  }
  .host-bar select, .host-bar input {
    font-size: 12px; padding: 6px 10px; border-radius: 999px;
    border: 1px solid var(--border); background: var(--card-2);
    color: var(--text); text-align: center;
  }
  .host-bar select { max-width: 220px; }
  .host-bar input { max-width: 150px; }

  .header-controls {
    display: flex; justify-content: space-between; align-items: center;
    gap: 8px; padding: 10px 0;
  }
  .header-controls select, .header-controls button {
    font-size: 12px; padding: 6px 10px; border-radius: 999px;
    border: 1px solid var(--border); background: var(--card-2);
    color: var(--text); cursor: pointer; width: auto; margin: 0;
  }

  /* ---------- TABS ---------- */
  .tab-bar {
    display: flex; gap: 6px; padding: 0 0 10px;
  }
  .tab-btn {
    flex: 1; padding: 9px 10px; border-radius: 999px; border: 1px solid var(--border);
    background: var(--card-2); color: var(--text-dim); font-size: 13px;
    font-weight: 600; cursor: pointer; margin: 0;
  }
  .tab-btn.active { background: var(--accent); color: white; border-color: var(--accent); }

  /* ---------- CONTAINER / CARDS ---------- */
  .container { padding: 0 16px; max-width: 560px; margin: 0 auto; }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 14px; margin-bottom: 14px;
  }
  .card h2 {
    font-size: 13px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--text-dim); margin: 0 0 10px;
  }
  details.card { padding: 0; overflow: hidden; }
  details.card summary {
    list-style: none; cursor: pointer; padding: 14px;
    font-size: 13px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--text-dim); font-weight: 700;
    display: flex; justify-content: space-between; align-items: center;
  }
  details.card summary::-webkit-details-marker { display: none; }
  details.card summary::after { content: "+"; font-size: 16px; color: var(--text-dim); }
  details.card[open] summary::after { content: "\\2212"; }
  details.card .inner { padding: 0 14px 14px; }

  label { display: block; font-size: 12px; color: var(--text-dim); margin: 8px 0 4px; }
  input[type=text], input[type=password], select {
    width: 100%; padding: 10px 12px; border-radius: 10px;
    border: 1px solid var(--border); background: var(--card-2);
    color: var(--text); font-size: 14px;
  }
  .row { display: flex; gap: 8px; }
  .row > * { flex: 1; }
  button.full {
    border: none; border-radius: 10px; padding: 11px 14px;
    font-size: 14px; font-weight: 600; margin-top: 10px;
    background: var(--accent); color: white; width: 100%;
    cursor: pointer;
  }
  button.full.secondary { background: var(--card-2); color: var(--text); }
  button.full.danger { background: var(--danger); color: white; }
  button:active { opacity: 0.8; }

  .btn-set-wrap { display: flex; justify-content: flex-end; margin-top: 12px; }
  .btn-set {
    border: none; border-radius: 10px; padding: 11px 28px;
    font-size: 14px; font-weight: 600;
    background: var(--accent); color: white; cursor: pointer;
  }
  .btn-set.danger { background: var(--danger); }

  #log {
    background: #0a0e18; border: 1px solid var(--border); border-radius: 10px;
    padding: 10px; font-family: "JetBrains Mono", monospace; font-size: 11.5px;
    white-space: pre-wrap; word-break: break-word;
    height: 220px; overflow-y: auto; color: #b9c2d8;
  }
  html[data-theme="light"] #log { background: #eef1f8; color: #29304a; }
  #log .ok { color: var(--accent-2); }
  #log .fail { color: var(--danger); }

  .footer-note { font-size: 11px; color: var(--text-dim); text-align: center; margin-top: 4px; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  body.view-stacked .tab-bar { display: none; }
  body.view-stacked .tab-content { display: block !important; }
  body.view-stacked .tab-content-label {
    font-size: 12px; font-weight: 700; text-transform: uppercase;
    color: var(--text-dim); margin: 4px 0 8px;
  }
  .tab-content-label { display: none; }
  body.view-stacked .tab-content-label { display: block; }
</style>
</head>
<body>

<header>
  <div class="header-top">
    <div class="logo-area">
      <svg width="36" height="36" viewBox="0 0 1200 1200" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="225" cy="788" rx="120" ry="121" fill="#E30613"/>
        <rect x="362" y="598" width="127" height="308" rx="16.5" fill="#E30613"/>
        <rect x="517" y="525" width="118" height="381" rx="15.34" fill="#E30613"/>
        <rect x="661" y="454" width="124" height="452" rx="16.12" fill="#1A4FBF"/>
        <rect x="809" y="377" width="128" height="529" rx="16.64" fill="#1A4FBF"/>
        <rect x="963" y="280" width="130" height="626" rx="16.9" fill="#FF7A00"/>
      </svg>
      <div class="logo-text">PT. PANDAWA<br>NUSANTARA<br>SOLUSINDO</div>
    </div>
    <div class="title-area">
      <h1>CIOT Modem Setup</h1>
      <div><span class="status-badge" id="statusBadge">belum login</span></div>
    </div>
  </div>

  <div class="host-bar">
    <select id="hostMode" onchange="onHostModeChange()">
      <option value="auto">192.168.1.1 (auto)</option>
      <option value="manual">Input manual (remote via IP)</option>
    </select>
    <input type="text" id="hostManual" placeholder="mis. 103.10.20.30"
           style="display:none;">
  </div>

  <div class="header-controls">
    <button id="themeToggle" onclick="toggleTheme()">&#9789; Tema</button>
    <select id="viewModeSelect" onchange="setViewMode(this.value)">
      <option value="tab">Tampilan: Tab</option>
      <option value="stacked">Tampilan: Susun</option>
    </select>
  </div>

  <div class="tab-bar">
    <button class="tab-btn active" data-tab="baca" onclick="switchTab('baca')">ADMIN LOGIN</button>
    <button class="tab-btn" data-tab="set" onclick="switchTab('set')">Set</button>
    <button class="tab-btn" data-tab="advance" onclick="switchTab('advance')">Advance</button>
  </div>
</header>

<div class="container">

  <!-- ================= TAB: ADMIN LOGIN ================= -->
  <div class="tab-content active" id="tab-baca">
    <div class="tab-content-label">Admin Login</div>

    <details class="card" open>
      <summary>Kredensial</summary>
      <div class="inner">
        <label>Username</label>
        <input type="text" id="username" placeholder="admin">
        <label>Password</label>
        <input type="password" id="password" placeholder="••••••">
        <div class="row">
          <button class="full secondary" onclick="doAction('check')">Cek Koneksi</button>
          <button class="full" onclick="doAction('login')">Login</button>
        </div>
      </div>
    </details>
  </div>

  <!-- ================= TAB: SET ================= -->
  <div class="tab-content" id="tab-set">
    <div class="tab-content-label">Set</div>

    <details class="card" open>
      <summary>WiFi — SSID, Max Client &amp; Password</summary>
      <div class="inner">
        <label>ESSID baru (kosongkan jika tidak diubah)</label>
        <input type="text" id="newEssid" placeholder="Nama WiFi baru">
        <label>Maximum Client</label>
        <input type="text" id="newMaxClient" placeholder="contoh: 8">
        <label>Password WiFi baru (kosongkan jika tidak diubah)</label>
        <input type="password" id="newWifiPass" placeholder="Password WiFi baru">
        <div class="btn-set-wrap">
          <button class="btn-set" onclick="doAction('apply_wifi')">SET</button>
        </div>
      </div>
    </details>

    <details class="card">
      <summary>Password Admin</summary>
      <div class="inner">
        <label>Password admin baru</label>
        <input type="password" id="newAdminPass" placeholder="Password admin baru">
        <div class="btn-set-wrap">
          <button class="btn-set" onclick="doAction('apply_admin')">SET</button>
        </div>
      </div>
    </details>

    <details class="card">
      <summary>WLAN Radio 2.4G — Basic</summary>
      <div class="inner">
        <label><input type="checkbox" id="radioEnableRf" checked style="width:auto;display:inline;">
          &nbsp;Enable Wireless RF</label>
        <label>Bandwidth</label>
        <select id="radioBandwidth">
          <option value="20Mhz" selected>20Mhz</option>
          <option value="40Mhz">40Mhz</option>
        </select>
        <label>Channel</label>
        <select id="radioChannel">
          <option value="1">1</option><option value="2">2</option>
          <option value="3">3</option><option value="4">4</option>
          <option value="5">5</option><option value="6">6</option>
          <option value="7">7</option><option value="8">8</option>
          <option value="9">9</option><option value="10">10</option>
          <option value="11" selected>11</option>
        </select>
        <div class="btn-set-wrap">
          <button class="btn-set" onclick="doAction('apply_radio')">SET</button>
        </div>
      </div>
    </details>

    <details class="card">
      <summary>WAN Connection (PPPoE)</summary>
      <div class="inner">
        <label><input type="checkbox" id="wanEnableVlan" style="width:auto;display:inline;">
          &nbsp;Enable VLAN</label>
        <label>VLAN ID</label>
        <input type="text" id="wanVlanId" value="100">
        <label>Service List</label>
        <select id="wanServiceList">
          <option value="TR069_VOICE_INTERNET" selected>TR069_VOICE_INTERNET</option>
          <option value="INTERNET">INTERNET</option>
          <option value="TR069">TR069</option>
          <option value="TR069_INTERNET">TR069_INTERNET</option>
          <option value="VOIP">VOIP</option>
          <option value="VOIP_INTERNET">VOIP_INTERNET</option>
          <option value="TR069_VOIP">TR069_VOIP</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label>PPP Username</label>
        <input type="text" id="wanUsername" placeholder="Username dari ISP">
        <label>PPP Password</label>
        <input type="password" id="wanPassword" placeholder="Password dari ISP">
        <div class="btn-set-wrap">
          <button class="btn-set" onclick="doAction('apply_wan')">SET</button>
        </div>
      </div>
    </details>

    <details class="card">
      <summary>Full Setup</summary>
      <div class="inner">
        <div class="footer-note" style="margin-bottom:8px;">
          Memakai semua nilai yang sudah diisi di kartu-kartu di atas —
          kosongkan field yang tidak ingin diubah sebelum menekan tombol ini.
        </div>
        <div class="btn-set-wrap">
          <button class="btn-set danger" onclick="doAction('full_setup')">SET</button>
        </div>
      </div>
    </details>
  </div>

  <!-- ================= TAB: ADVANCE ================= -->
  <div class="tab-content" id="tab-advance">
    <div class="tab-content-label">Advance</div>

    <div class="card">
      <h2>Baca Konfigurasi</h2>
      <label>Halaman</label>
      <select id="readPage">
        <option value="radio">Radio / Channel</option>
        <option value="essid">ESSID</option>
        <option value="security">Security / Password WiFi</option>
        <option value="admin_user">User Admin</option>
      </select>
      <button class="full secondary" onclick="doAction('read')">Baca</button>
    </div>

    <div class="card">
      <h2>Daftar Modem</h2>
      <div class="footer-note" style="margin-bottom:8px; text-align:left;">
        Saat ini tool hanya mendukung otomasi penuh untuk CIOT GM220-S XPON.
        Gunakan "+ Tambah Modem Baru" untuk mencatat modem jenis lain sebagai
        referensi — otomasinya akan menyusul.
      </div>
      <div id="modemProfileList" style="margin-bottom:10px; font-size:13px;">
        <div>• CIOT GM220-S XPON (bawaan, sudah didukung penuh)</div>
      </div>
      <details class="card" style="margin:0;">
        <summary>+ Tambah Modem Baru</summary>
        <div class="inner">
          <label>Nama / Merk Modem</label>
          <input type="text" id="modemProfileName" placeholder="mis. ZTE F609">
          <label>Host/IP default</label>
          <input type="text" id="modemProfileHost" placeholder="mis. 192.168.1.1">
          <label>Catatan</label>
          <input type="text" id="modemProfileNotes" placeholder="opsional">
          <div class="btn-set-wrap">
            <button class="btn-set" onclick="doAction('register_modem')">SIMPAN</button>
          </div>
        </div>
      </details>
    </div>
  </div>

  <!-- ============ RINGKASAN + LOG (tampil di setiap tab) ============ -->
  <div class="card">
    <h2>Ringkasan / Report</h2>
    <div class="footer-note" style="margin-bottom:8px;">
      Ambil info Device, WiFi, WAN, dan PON untuk disalin/kirim (mis. ke Telegram).
    </div>
    <div class="row">
      <button class="full secondary" onclick="doAction('summary')">Ambil Ringkasan</button>
      <button class="full secondary" onclick="copyLog()">Copy</button>
    </div>
    <div class="footer-note" style="margin:10px 0 6px;">
      Info untuk dibagikan ke pelanggan (nama WiFi &amp; password):
    </div>
    <button class="full secondary" onclick="doAction('customer_share')">Bagikan ke Pelanggan</button>

    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">
      <div style="font-size:12px;font-weight:700;color:var(--accent-2);margin-bottom:6px">
        🔗 Kirim ke Database PNS.NET
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;line-height:1.5">
        Setelah login modem, kirim ringkasan teknis (SN, MAC, SSID, OPM, WAN username)
        ke database PNS.NET — menghubungkan data modem ke data pelanggan.
      </div>
      <label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:3px">
        Token PNS.NET
      </label>
      <input type="password" id="pnsnetToken"
        placeholder="Token dari login web app PNS.NET..."
        style="width:100%;padding:8px 10px;border-radius:8px;
               border:1px solid var(--border);background:var(--card-2);
               color:var(--text);font-size:12px;font-family:monospace;margin-bottom:8px">
      <label style="font-size:12px;color:var(--text-dim);display:block;margin-bottom:3px">
        Keterangan (opsional)
      </label>
      <input type="text" id="pnsnetKet"
        placeholder="Pemasangan baru / pengecekan rutin / troubleshooting..."
        style="width:100%;padding:8px 10px;border-radius:8px;
               border:1px solid var(--border);background:var(--card-2);
               color:var(--text);font-size:12px;margin-bottom:10px">
      <div class="row">
        <button class="full btn-primary" style="font-size:13px"
          onclick="kirimPnsnet(false)">🚀 Kirim & Update Database</button>
        <button class="secondary" style="padding:10px 14px;font-size:12px"
          onclick="kirimPnsnet(true)">📝 Log</button>
      </div>
      <div id="pnsnetStatus" style="font-size:12px;margin-top:8px;min-height:20px"></div>
    </div>
  </div>

  <div class="card">
    <h2>Log</h2>
    <div id="log">Menunggu aksi pertama...</div>
  </div>

  <div class="footer-note">PT. Pandawa Nusantara Solusindo — server lokal, hanya bisa diakses dari HP ini (127.0.0.1).</div>
</div>

<script>
function appendLog(text, ok) {
  const el = document.getElementById('log');
  const span = document.createElement('div');
  span.className = ok === true ? 'ok' : (ok === false ? 'fail' : '');
  span.textContent = text;
  el.appendChild(span);
  el.scrollTop = el.scrollHeight;
}

function setStatus(loggedIn) {
  const b = document.getElementById('statusBadge');
  if (loggedIn) {
    b.textContent = 'sudah login';
    b.classList.add('on');
  } else {
    b.textContent = 'belum login';
    b.classList.remove('on');
  }
}

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === name);
  });
  document.querySelectorAll('.tab-content').forEach(c => {
    c.classList.toggle('active', c.id === 'tab-' + name);
  });
  localStorage.setItem('ciot_active_tab', name);
}

function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  html.setAttribute('data-theme', next);
  localStorage.setItem('ciot_theme', next);
}

function setViewMode(mode) {
  document.body.classList.toggle('view-stacked', mode === 'stacked');
  localStorage.setItem('ciot_view_mode', mode);
}

function onHostModeChange() {
  const mode = document.getElementById('hostMode').value;
  const manualInput = document.getElementById('hostManual');
  manualInput.style.display = mode === 'manual' ? 'inline-block' : 'none';
  localStorage.setItem('ciot_host_mode', mode);
}

function getCurrentHost() {
  const mode = document.getElementById('hostMode').value;
  if (mode === 'manual') {
    const v = document.getElementById('hostManual').value.trim();
    return v || null;
  }
  return null; // null = pakai default 192.168.1.1 di backend
}

function copyLog() {
  const text = document.getElementById('log').innerText;
  if (!text || text.trim() === '') {
    appendLog('[INFO] Tidak ada isi log untuk disalin.');
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    appendLog('[OK] Log disalin ke clipboard.', true);
  }).catch(e => {
    appendLog('[GAGAL] Tidak bisa menyalin ke clipboard: ' + e, false);
  });
}

(function restorePrefs() {
  const theme = localStorage.getItem('ciot_theme');
  if (theme) document.documentElement.setAttribute('data-theme', theme);

  const tab = localStorage.getItem('ciot_active_tab');
  if (tab) switchTab(tab);

  const view = localStorage.getItem('ciot_view_mode');
  if (view) {
    document.getElementById('viewModeSelect').value = view;
    setViewMode(view);
  }

  const hostMode = localStorage.getItem('ciot_host_mode');
  if (hostMode) {
    document.getElementById('hostMode').value = hostMode;
    onHostModeChange();
  }
  const hostManual = localStorage.getItem('ciot_host_manual');
  if (hostManual) document.getElementById('hostManual').value = hostManual;
})();

async function doAction(action) {
  const hostManualVal = document.getElementById('hostManual').value.trim();
  if (hostManualVal) localStorage.setItem('ciot_host_manual', hostManualVal);

  const payload = {
    action: action,
    host: getCurrentHost(),
    username: document.getElementById('username').value,
    password: document.getElementById('password').value,
    read_page: document.getElementById('readPage').value,
    new_essid: document.getElementById('newEssid').value,
    new_max_client: document.getElementById('newMaxClient').value,
    new_wifi_pass: document.getElementById('newWifiPass').value,
    new_admin_pass: document.getElementById('newAdminPass').value,
    wan_enable_vlan: document.getElementById('wanEnableVlan').checked,
    wan_vlan_id: document.getElementById('wanVlanId').value,
    wan_service_list: document.getElementById('wanServiceList').value,
    wan_username: document.getElementById('wanUsername').value,
    wan_password: document.getElementById('wanPassword').value,
    radio_enable_rf: document.getElementById('radioEnableRf').checked,
    radio_bandwidth: document.getElementById('radioBandwidth').value,
    radio_channel: document.getElementById('radioChannel').value,
    modem_profile_name: document.getElementById('modemProfileName').value,
    modem_profile_host: document.getElementById('modemProfileHost').value,
    modem_profile_notes: document.getElementById('modemProfileNotes').value,
  };
  appendLog('--- menjalankan: ' + action + ' ---');
  try {
    const res = await fetch('/api/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    appendLog(data.log, data.ok);
    if (typeof data.logged_in === 'boolean') {
      setStatus(data.logged_in);
    }
  } catch (e) {
    appendLog('[GAGAL] Tidak bisa menghubungi server lokal: ' + e, false);
  }
}

// ── Kirim ke PNS.NET ─────────────────────────────────────
async function kirimPnsnet(logOnly) {
  const token = document.getElementById('pnsnetToken').value.trim();
  const ket   = document.getElementById('pnsnetKet').value.trim();
  const stEl  = document.getElementById('pnsnetStatus');
  if (!token) {
    stEl.style.color = 'var(--danger)';
    stEl.textContent = '❌ Isi token PNS.NET dulu';
    return;
  }
  stEl.style.color = 'var(--text-dim)';
  stEl.textContent = '⟳ Mengirim ke PNS.NET...';
  try {
    const res = await fetch('/api/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        action: 'kirim_pnsnet',
        pnsnet_token: token,
        keterangan: ket,
        log_only: logOnly,
      }),
    });
    const data = await res.json();
    if (data.log) appendLog(data.log, data.ok);
    if (data.ok) {
      stEl.style.color = 'var(--accent-2)';
      stEl.textContent = logOnly
        ? '✅ Log dicatat di PNS.NET'
        : '✅ Berhasil dikirim ke PNS.NET';
    } else {
      stEl.style.color = 'var(--danger)';
      stEl.textContent = '❌ ' + (data.log || 'Gagal');
    }
  } catch(e) {
    stEl.style.color = 'var(--danger)';
    stEl.textContent = '❌ Error: ' + e.message;
  }
}
</script>

</body>
</html>
"""


# ------------------------------------------------------------
# LOGIKA AKSI — reuse fungsi dari ciot_setup.py, tangkap print()
# ------------------------------------------------------------
def run_captured(fn, *args, **kwargs):
    """Jalankan fn(), tangkap semua print() jadi teks log."""
    buf = io.StringIO()
    ok = None
    try:
        with contextlib.redirect_stdout(buf):
            result = fn(*args, **kwargs)
        if isinstance(result, bool):
            ok = result
    except Exception as e:
        buf.write(f"\n[EXCEPTION] {e}\n")
        ok = False
    return buf.getvalue().strip(), ok


def apply_credentials(payload):
    if payload.get("username"):
        config.LOGIN_USERNAME = payload["username"]
    if payload.get("password"):
        config.LOGIN_PASSWORD = payload["password"]


def apply_host(payload):
    """
    Kalau mode host = manual dan diisi IP berbeda, timpa config.HOST/BASE_URL
    untuk request selanjutnya (dipakai untuk remote ke modem pelanggan
    lewat IP publik/VPN, bukan cuma 192.168.1.1 lokal).
    """
    host = (payload.get("host") or "").strip()
    if host and host != config.HOST:
        config.HOST = host
        config.BASE_URL = f"http://{host}"
    elif not host and config.HOST != "192.168.1.1":
        # mode auto dipilih lagi -> kembali ke default
        config.HOST = "192.168.1.1"
        config.BASE_URL = f"http://{config.HOST}"


# Daftar modem non-CIOT yang dicatat teknisi (stub, in-memory saja,
# hilang saat server di-restart). Otomasi untuk merk lain belum dibuat.
REGISTERED_MODEMS = []


def handle_action(payload):
    action = payload.get("action")
    apply_credentials(payload)
    apply_host(payload)

    if action == "check":
        def _run():
            ok_conn = core.check_connection()
            if core.session.logged_in:
                essid = core.get_current_essid()
                print(f"Nama WiFi saat ini: {essid if essid else '(tidak ditemukan)'}")
            else:
                print("Nama WiFi: (login dulu untuk menampilkan nama WiFi)")
            return ok_conn
        log, ok = run_captured(_run)

    elif action == "login":
        log, ok = run_captured(core.login)

    elif action == "read":
        page_key = payload.get("read_page", "essid")
        log, ok = run_captured(core.read_config, page_key)
        ok = log is not None and "[GAGAL]" not in log

    elif action == "apply_wifi":
        essid_val = payload.get("new_essid", "").strip()
        max_client = payload.get("new_max_client", "").strip()
        wifi_pass = payload.get("new_wifi_pass", "").strip()
        if not essid_val and not max_client and not wifi_pass:
            return "ESSID, Max Client, dan Password WiFi kosong — tidak ada yang dikirim.", None
        if not core.session.logged_in:
            return "[GAGAL] Belum login. Tekan tombol Login dahulu.", False
        def _run():
            ok_all = True
            if essid_val or max_client:
                fields = core.build_essid_fields(
                    core.session.session_token, essid_val or None, max_client or None
                )
                result = core.apply_config("essid", fields)
                if result and essid_val:
                    core.verify_change("essid", "essid", essid_val)
                else:
                    ok_all = ok_all and result
            if wifi_pass:
                fields = core.build_security_fields(core.session.session_token, wifi_pass)
                if not core.apply_config("security", fields):
                    ok_all = False
            return ok_all
        log, ok = run_captured(_run)

    elif action == "apply_admin":
        val = payload.get("new_admin_pass", "").strip()
        if not val:
            return "Password admin baru kosong — tidak ada yang dikirim.", None
        if not core.session.logged_in:
            return "[GAGAL] Belum login. Tekan tombol Login dahulu.", False
        def _run():
            fields = core.build_admin_password_fields(
                core.session.session_token, val
            )
            return core.apply_config("admin_user", fields)
        log, ok = run_captured(_run)

    elif action == "apply_wan":
        if not core.session.logged_in:
            return "[GAGAL] Belum login. Tekan tombol Login dahulu.", False
        enable_vlan = payload.get("wan_enable_vlan")
        vlan_id = payload.get("wan_vlan_id", "").strip()
        service_list = payload.get("wan_service_list", "").strip()
        username = payload.get("wan_username", "").strip()
        password = payload.get("wan_password", "").strip()
        def _run():
            return core.apply_wan(
                enable_vlan=enable_vlan if enable_vlan else None,
                vlan_id=vlan_id or None,
                service_list_label=service_list or None,
                username=username or None,
                password=password or None,
            )
        log, ok = run_captured(_run)

    elif action == "apply_radio":
        if not core.session.logged_in:
            return "[GAGAL] Belum login. Tekan tombol Login dahulu.", False
        enable_rf = payload.get("radio_enable_rf")
        bandwidth = payload.get("radio_bandwidth", "").strip()
        channel = payload.get("radio_channel", "").strip()
        def _run():
            fields = core.build_radio_fields(
                core.session.session_token,
                enable_rf=enable_rf, bandwidth=bandwidth or None,
                channel=channel or None,
            )
            return core.apply_config("radio", fields)
        log, ok = run_captured(_run)

    elif action == "summary":
        if not core.session.logged_in:
            return "[GAGAL] Belum login. Tekan tombol Login dahulu.", False
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report_text = core.get_summary_report()
        log = (buf.getvalue().strip() + "\n\n" + report_text).strip()
        ok = True

    elif action == "full_setup":
        config.NEW_ESSID = payload.get("new_essid", "").strip() or None
        config.NEW_MAX_CLIENT = payload.get("new_max_client", "").strip() or None
        config.NEW_WIFI_PASSWORD = payload.get("new_wifi_pass", "").strip() or None
        config.NEW_ADMIN_PASSWORD = payload.get("new_admin_pass", "").strip() or None
        wan_enable_vlan = payload.get("wan_enable_vlan")
        wan_vlan_id = payload.get("wan_vlan_id", "").strip()
        wan_service_list = payload.get("wan_service_list", "").strip()
        wan_username = payload.get("wan_username", "").strip()
        wan_password = payload.get("wan_password", "").strip()
        radio_enable_rf = payload.get("radio_enable_rf")
        radio_bandwidth = payload.get("radio_bandwidth", "").strip()
        radio_channel = payload.get("radio_channel", "").strip()

        def _run():
            ok_all = True
            if not core.check_connection():
                return False
            if not core.login():
                return False
            if config.NEW_ESSID or config.NEW_MAX_CLIENT:
                fields = core.build_essid_fields(
                    core.session.session_token,
                    config.NEW_ESSID, config.NEW_MAX_CLIENT
                )
                if core.apply_config("essid", fields):
                    if config.NEW_ESSID:
                        core.verify_change("essid", "essid", config.NEW_ESSID)
                else:
                    ok_all = False
            if config.NEW_WIFI_PASSWORD:
                fields = core.build_security_fields(
                    core.session.session_token, config.NEW_WIFI_PASSWORD
                )
                if not core.apply_config("security", fields):
                    ok_all = False
            if config.NEW_ADMIN_PASSWORD:
                fields = core.build_admin_password_fields(
                    core.session.session_token, config.NEW_ADMIN_PASSWORD
                )
                if not core.apply_config("admin_user", fields):
                    ok_all = False
            if wan_vlan_id or wan_username or wan_password:
                if not core.apply_wan(
                    enable_vlan=wan_enable_vlan if wan_enable_vlan else None,
                    vlan_id=wan_vlan_id or None,
                    service_list_label=wan_service_list or None,
                    username=wan_username or None,
                    password=wan_password or None,
                ):
                    ok_all = False
            if radio_bandwidth or radio_channel:
                fields = core.build_radio_fields(
                    core.session.session_token,
                    enable_rf=radio_enable_rf if radio_enable_rf else None,
                    bandwidth=radio_bandwidth or None,
                    channel=radio_channel or None,
                )
                if not core.apply_config("radio", fields):
                    ok_all = False
            print("\n--- Ringkasan setelah Full Setup ---")
            print(core.get_summary_report())
            return ok_all
        log, ok = run_captured(_run)

    elif action == "customer_share":
        if not core.session.logged_in:
            return "[GAGAL] Belum login. Tekan tombol Login dahulu.", False
        typed_pass = payload.get("new_wifi_pass", "").strip()
        def _run():
            essid = core.get_current_essid()
            lines = []
            lines.append(f"WiFi: {essid if essid else '(tidak ditemukan)'}")
            if typed_pass:
                lines.append(f"Password: {typed_pass}")
            else:
                lines.append(
                    "Password: (tidak bisa dibaca ulang dari modem — "
                    "isi dulu field Password WiFi di kartu Set jika baru "
                    "saja diganti, atau catat manual saat set pertama kali)"
                )
            print("\n".join(lines))
            return True
        log, ok = run_captured(_run)

    elif action == "register_modem":
        name = payload.get("modem_profile_name", "").strip()
        host = payload.get("modem_profile_host", "").strip()
        notes = payload.get("modem_profile_notes", "").strip()
        if not name:
            return "Nama/merk modem kosong — tidak disimpan.", None
        REGISTERED_MODEMS.append({"name": name, "host": host, "notes": notes})
        log = (f"[OK] Modem '{name}' dicatat"
               f"{' (host: ' + host + ')' if host else ''}. "
               f"Otomasi untuk modem ini belum tersedia — baru dicatat "
               f"sebagai referensi untuk pengembangan berikutnya.")
        ok = True

    elif action == "kirim_pnsnet":
        token    = payload.get("pnsnet_token", "").strip()
        log_only = payload.get("log_only", False)
        ket      = payload.get("keterangan", "").strip()
        if not token:
            return "[GAGAL] Token PNS.NET kosong.", False
        if not core.session.logged_in:
            return "[GAGAL] Belum login ke modem — login dulu.", False

        buf2 = io.StringIO()
        summary_data = {}
        with contextlib.redirect_stdout(buf2):
            try:
                dev = core.get_device_info()
                if dev:
                    summary_data["serial_number"] = dev.get("serial Number", "")
                    summary_data["mac_address"]   = dev.get("MAC", "")
                    summary_data["firmware_info"] = dev.get("Software Version", "")
                summary_data["ssid_wifi"]   = core.get_current_essid() or ""
                summary_data["max_client"]  = core.get_current_max_client() or ""
                summary_data["wan_username"]= core.get_wan_username() or ""
                summary_data["pon_rx_power"]= core.get_pon_optical_power() or ""
                wan = core.get_wan_status()
                if wan:
                    summary_data["wan_type"]            = wan.get("Type", "PPPoE")
                    summary_data["wan_connection_name"] = wan.get("Connection Name", "")
                    summary_data["ip_address"]          = wan.get("IP", "")
            except Exception as e:
                print(f"[ERROR ambil data] {e}")

        extra_log = buf2.getvalue().strip()
        if not summary_data.get("serial_number") and not summary_data.get("wan_username"):
            return (extra_log + "\n[GAGAL] Data modem kosong."), False

        action_name = "ciot_log_only" if log_only else "ciot_kirim_ringkasan"
        post_payload = {
            "action": action_name, "token": token,
            "payload": {
                "serial_number"       : summary_data.get("serial_number", ""),
                "mac_address"         : summary_data.get("mac_address", ""),
                "ip_address"          : summary_data.get("ip_address", ""),
                "ssid_wifi"           : summary_data.get("ssid_wifi", ""),
                "max_client"          : summary_data.get("max_client", ""),
                "wan_username"        : summary_data.get("wan_username", ""),
                "pon_rx_power"        : summary_data.get("pon_rx_power", ""),
                "wan_type"            : summary_data.get("wan_type", "PPPoE"),
                "wan_connection_name" : summary_data.get("wan_connection_name", ""),
                "firmware_info"       : summary_data.get("firmware_info", ""),
                "keterangan"          : ket,
            }
        }
        try:
            import urllib.request as _ureq, urllib.error as _uerr
            req = _ureq.Request(
                PNSNET_API_URL,
                data=json.dumps(post_payload).encode(),
                headers={"Content-Type": "text/plain"}, method="POST")
            with _ureq.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode())
            if result.get("ok"):
                d = result.get("data", {})
                linked = d.get("linked", False)
                nama   = d.get("pelanggan", "")
                if log_only:
                    log = extra_log + "\n[OK] Log dicatat di PNS.NET."
                elif linked:
                    log = extra_log + f"\n[OK] Tersimpan — terhubung ke pelanggan: {nama}"
                else:
                    log = extra_log + "\n[OK] Tersimpan (WAN username belum terdaftar sebagai pelanggan aktif)"
                ok = True
            else:
                log = extra_log + f"\n[GAGAL] PNS.NET: {result.get('error','unknown')}"
                ok  = False
        except Exception as e:
            log = extra_log + f"\n[GAGAL] {e}"
            ok  = False

    else:
        log, ok = f"Aksi tidak dikenal: {action}", False

    return log, ok


# ------------------------------------------------------------
# HTTP SERVER (stdlib saja)
# ------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # bungkam log akses default supaya terminal tidak berisik

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = PAGE_HTML.replace("__HOST__", config.HOST)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/api/action":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json({"log": "[GAGAL] Payload tidak valid.", "ok": False})
            return

        log_text, ok = handle_action(payload)
        self._send_json({
            "log": log_text,
            "ok": ok,
            "logged_in": core.session.logged_in,
        })

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def try_open_browser():
    try:
        subprocess.run(
            ["termux-open-url", f"http://127.0.0.1:{PORT}"],
            timeout=5, check=False,
        )
    except Exception:
        pass


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"CIOT Modem Setup — Web UI berjalan.")
    print(f"Buka browser ke: http://127.0.0.1:{PORT}")
    print("Tekan Ctrl+C untuk berhenti.\n")
    try_open_browser()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")


if __name__ == "__main__":
    main()
