# PNS.NET — Referensi Konfigurasi Terpusat
**PT. Pandawa Nusantara Solusindo**
Dokumen ini berisi semua credential, ID, URL, dan token yang dipakai di seluruh sistem PNS.NET.
Update di sini jika ada perubahan, lalu sesuaikan di file yang merujuk ke nilai ini.

---

## 1. Google Apps Script (Backend API)

### Deployment URL
```
[Disimpan privat; jangan commit URL deployment.]
```
**Dipakai di:**
- `index.html` (GitHub Pages) — untuk login, sync data
- `bridge.py` / `web_ui.py` (Termux) — untuk kirim ringkasan modem
- `config.py` (Termux) — konstanta `PNSNET_API_URL`

**Cara update jika URL berubah:**
Setiap "New version" deployment di Apps Script menghasilkan URL yang SAMA selama pakai deployment yang sama (bukan buat deployment baru). Jika terpaksa buat deployment baru, update semua file di atas.

### Project Name
```
PNS-NET Central Setup
```

### Kredensial Login (disimpan privat)
```
Username dan password tidak disimpan di repository publik.
Simpan melalui Apps Script Script Properties dan gunakan akun individual.
```

---

## 2. Google Spreadsheet IDs

| Nama Spreadsheet | ID | Isi |
|---|---|---|
| PNS_NET_WILAYAH | `[Disimpan di konfigurasi privat]` | Wilayah, sub-wilayah |
| PNS_NET_JARINGAN_FO | `[Disimpan di konfigurasi privat]` | OLT, ODC, ODP, Port, Kabel, Server |
| PNS_NET_SDM | `[Disimpan di konfigurasi privat]` | Karyawan, Teknisi, User, Role, Permission |
| PNS_NET_PELANGGAN | `[Disimpan di konfigurasi privat]` | Calon, Pemasangan, Pelanggan |
| PNS_NET_INVENTORI | `[Disimpan di konfigurasi privat]` | Modem, Material, Stok, Log Konfigurasi |
| PNS_NET_KEUANGAN | `[Disimpan di konfigurasi privat]` | Tagihan, Pembayaran, Setoran |

**Dipakai di:** `Api.gs` → konstanta `SS_IDS`

### Google Drive — Folder Gallery Pelanggan
```
Folder ID : [Disimpan di konfigurasi privat]
Path      : /PNS.NET/gallery pelanggan/
```
**Dipakai di:** `Api.gs` → `SS_IDS.GALLERY_FOLDER`

---

## 3. Telegram Bot

### Bot Token
```
Simpan di Apps Script → Script Properties → key: TG_BOT_TOKEN
Nilai: [isi bot token dari @BotFather]
```
> ⚠️ Jangan tulis token di file yang di-push ke GitHub

### Chat ID Supergroup
```
Simpan di Apps Script → Script Properties → key: TG_CHAT_ID
Nilai: -100xxxxxxxxxx (format supergroup, awalan -100)
```

### Topic IDs
| # | Nama Topik | Topic ID | Key di Script Properties |
|---|---|---|---|
| 1 | Pengumuman | `4` | `TG_TOPIC_PENGUMUMAN` |
| 2 | Pelanggan Baru | `6` | `TG_TOPIC_PELANGGAN` |
| 3 | Pembayaran | `7` | `TG_TOPIC_PEMBAYARAN` |
| 4 | Teknis & Pemasangan | `8` | `TG_TOPIC_TEKNIS` |
| 5 | Gangguan & Keluhan | `9` | `TG_TOPIC_GANGGUAN` |
| 6 | Inventori & Stok | `10` | `TG_TOPIC_INVENTORI` |
| 7 | Review Data | `11` | `TG_TOPIC_REVIEW` |
| 8 | Chat AI | — | Coming soon |

**Dipakai di:**
- `TelegramNotif.gs` → konstanta `TG.TOPICS`
- `Api.gs` → `ciotNotifTelegram_()` untuk notif modem
- `bridge.py` / `web_ui.py` → via API PNS.NET (tidak langsung)

**Cara set di Apps Script:**
```javascript
// Jalankan sekali di Apps Script
function setupTelegramConfig() {
  const props = PropertiesService.getScriptProperties();
  props.setProperty('TG_BOT_TOKEN',         'ISI_DI_SINI');
  props.setProperty('TG_CHAT_ID',           'ISI_DI_SINI');
  props.setProperty('TG_TOPIC_PENGUMUMAN',  '4');
  props.setProperty('TG_TOPIC_PELANGGAN',   '6');
  props.setProperty('TG_TOPIC_PEMBAYARAN',  '7');
  props.setProperty('TG_TOPIC_TEKNIS',      '8');
  props.setProperty('TG_TOPIC_GANGGUAN',    '9');
  props.setProperty('TG_TOPIC_INVENTORI',   '10');
  props.setProperty('TG_TOPIC_REVIEW',      '11');
}
```

---

## 4. GitHub

### Repositories
| Repo | URL | Isi | GitHub Pages |
|---|---|---|---|
| pns-net-app | `github.com/petugas-pandawa/pns-net-app` | Web app operasional | `petugas-pandawa.github.io/pns-net-app/` |
| ciot-modem-tool | `github.com/petugas-pandawa/ciot-modem-tool` | CIOT Bridge + driver modem | Tidak (lokal Termux) |

### File penting per repo

**pns-net-app:**
```
index.html    ← Web app utama (dashboard, calon, pemasangan, login)
manifest.json ← PWA manifest
sw.js         ← Service worker (cache, offline)
```

**ciot-modem-tool:**
```
bridge.py         ← Server utama v2.0 (port 8088)
web_ui.py         ← UI lama (tetap dipakai, port 8088)
config.py         ← Konfigurasi lokal (TIDAK di-push, ada di .gitignore)
config_template.py← Template config untuk onboarding HP baru
ciot_setup.py     ← Logika HTTP modem CIOT (tidak diubah)
modem/
  __init__.py     ← Registry driver
  base.py         ← Kontrak standar semua driver
  ciot.py         ← Driver CIOT GM220-S XPON
  manual.py       ← Driver mode manual
start-ciot.sh     ← Shortcut auto-launch bridge + browser
```

### Personal Access Token (PAT)
```
Lokasi: github.com → Settings → Developer settings
        → Personal access tokens → Tokens (classic)
Scope : repo
Pakai : sebagai password saat git push dari Termux
```
> ⚠️ Token PAT expire — generate ulang jika git push diminta password lagi

---

## 5. Termux — File & Port

### Lokasi file
```
~/ciot-modem-tool/   ← Project CIOT Bridge
~/pns-net-app/       ← Clone repo web app (untuk git push)
~/start-ciot.sh      ← Shortcut auto-launch
~/.shortcuts/        ← Shortcut untuk Termux Widget
```

### Port yang dipakai
```
8088  ← CIOT Bridge (bridge.py / web_ui.py)
       Akses: http://127.0.0.1:8088
```

### Perintah rutin
```bash
# Jalankan CIOT Bridge
~/start-ciot.sh

# Update web app ke GitHub
cd ~/pns-net-app
git pull
# (edit/copy index.html)
git add index.html
git commit -m "pesan commit"
git push

# Update CIOT Tool dari GitHub
cd ~/ciot-modem-tool
git pull
```

---

## 6. Server Mikrotik / PPPoE

### Server aktif
| Nama | Suffix | Tipe | Input dari |
|---|---|---|---|
| Ogoamas | `@ogoamas` | Pusat | Tower |
| Bangkir | `@bangkir` | Sub | Output @ogoamas |

**Format username PPPoE:**
```
{4_digit_urut}{nama_ktp_lowercase}.{nama_desa_lowercase}@{server}
Contoh: 0042budisantoso.tambu@ogoamas
```
**Dipakai di:** `Api.gs` → `generateUsernamePPPoE_()`

---

## 7. Cara Update Jika Ada Perubahan

### Apps Script URL baru
1. Update di `index.html` → cari `AKfycby...` → ganti URL baru
2. Update di `bridge.py` → konstanta `PNSNET_API_URL`
3. Update di `config.py` (Termux) → `PNSNET_API_URL`
4. Update dokumen ini

### Tambah server baru (selain @ogoamas & @bangkir)
1. Jalankan di Apps Script:
```javascript
// Di sheet MASTER_SERVER (PNS_NET_JARINGAN_FO)
// Tambah row baru: id, nama, suffix, tipe, id_parent, status
```
2. Update dokumen ini di bagian Server Mikrotik

### Tambah topik Telegram baru
1. Buat topik di Supergroup
2. Kirim pesan di topik → jalankan `getTopicIds()` di Apps Script
3. Tambah key di `setupTelegramConfig()`
4. Tambah di `TelegramNotif.gs` → konstanta `TG.TOPICS`
5. Update tabel di dokumen ini

### Tambah driver modem baru
1. Buat file `modem/{nama}.py` ikuti kontrak `ModemBase`
2. Register di `modem/__init__.py`
3. Push ke GitHub → `git pull` di semua HP teknisi
4. Update dokumen ini

---

*Terakhir diupdate: Oktober 2026*
*Versi sistem: PNS.NET v2.0*
