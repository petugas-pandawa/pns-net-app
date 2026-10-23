// ============================================================
// API.GS — Central Router PNS.NET Multi-Spreadsheet
// ============================================================

// ── SPREADSHEET IDs ────────────────────────────────────────
// Spreadsheet and Drive identifiers are configured only in Apps Script Script Properties.
const SS_PROP_KEYS = Object.freeze({
  WILAYAH: 'SS_WILAYAH',
  JARINGAN: 'SS_JARINGAN',
  SDM: 'SS_SDM',
  PELANGGAN: 'SS_PELANGGAN',
  INVENTORI: 'SS_INVENTORI',
  KEUANGAN: 'SS_KEUANGAN',
  GALLERY_FOLDER: 'SS_GALLERY_FOLDER',
});

// ── Buka spreadsheet (cache sederhana per eksekusi) ────────
const _ssCache = {};
function getRequiredScriptProperty_(key) {
  const value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) throw new Error('Script Property belum diset: ' + key);
  return value;
}

function getSS_(key) {
  const propName = SS_PROP_KEYS[key];
  if (!propName) throw new Error('Spreadsheet key tidak dikenal: ' + key);
  if (!_ssCache[key]) {
    _ssCache[key] = SpreadsheetApp.openById(getRequiredScriptProperty_(propName));
  }
  return _ssCache[key];
}

// ── Response helper ────────────────────────────────────────
function ok_(data) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, data }))
    .setMimeType(ContentService.MimeType.JSON);
}
function err_(msg, code) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: false, error: msg, code: code || 400 }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── Token auth ─────────────────────────────────────────────
function verifyToken_(token) {
  if (!token) return null;
  try {
    const props = PropertiesService.getScriptProperties();
    const secret = props.getProperty('API_SECRET');
    if (!secret) return null;
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const [header, payload, sig] = parts;
    const expected = Utilities.base64Encode(
      Utilities.computeHmacSha256Signature(header + '.' + payload, secret)
    );
    if (sig !== expected) return null;
    const data = JSON.parse(Utilities.newBlob(
      Utilities.base64Decode(payload)).getDataAsString());
    if (!data || !Number.isFinite(Number(data.exp)) || Number(data.exp) <= Date.now() || !data.sub || !Array.isArray(data.permissions)) return null;
    return data;
  } catch(e) { return null; }
}

function makeToken_(userId, role, permissions) {
  const props  = PropertiesService.getScriptProperties();
  const secret = props.getProperty('API_SECRET');
  if (!secret) throw new Error('Script Property API_SECRET belum diset');
  const header  = Utilities.base64Encode(JSON.stringify({ alg:'HS256', typ:'JWT' }));
  const payload = Utilities.base64Encode(JSON.stringify({
    sub: userId,
    role,
    permissions,
    exp: Date.now() + (30 * 24 * 60 * 60 * 1000), // 30 hari
    iat: Date.now()
  }));
  const sig = Utilities.base64Encode(
    Utilities.computeHmacSha256Signature(header + '.' + payload, secret)
  );
  return `${header}.${payload}.${sig}`;
}

// ── doGet - Health check only; data/auth requests require POST ─
function doGet(e) {
  if (!e || !e.parameter || !e.parameter.action) {
    return ok_({ status: 'PNS.NET API aktif', ts: new Date().toISOString() });
  }
  return err_('Endpoint data hanya menerima POST; parameter sensitif di URL dinonaktifkan.', 405);
}

// ── doPost — Main router ───────────────────────────────────
function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch(_) {
    return err_('Body bukan JSON valid');
  }

  const { action } = body;

  // ── Login tidak perlu token ────────────────────────────
  if (action === 'login') return handleLogin_(body);

  // ── Semua action lain wajib token ─────────────────────
  const user = verifyToken_(body.token);
  if (!user) return err_('Token tidak valid atau kadaluarsa', 401);

  switch (action) {
    case 'bayar_catat':
      return requirePermission_(user, 'KEUANGAN_WRITE', () => handleBayarCatat_(body, user));
    case 'bayar_konfirmasi':
      return requirePermission_(user, 'KASIR_KONFIRMASI', () => handleBayarKonfirmasi_({ id_pembayaran: body.id_pembayaran || '', aksi: body.aksi || '' }, user));
    case 'bayar_rekap':
      return handleBayarRekap_({ bulan: body.bulan || '', tahun: body.tahun || '' }, user);
    case 'bayar_list_belum':
      return handleBayarListBelum_({}, user);
    case 'bayar_upload_belum': {
      let rows = body.rows;
      if (typeof rows === 'string') {
        try { rows = JSON.parse(rows); } catch (_) { return err_('rows tidak valid JSON'); }
      }
      if (!Array.isArray(rows)) return err_('rows harus array');
      return requirePermission_(user, 'KEUANGAN_WRITE', () => handleBayarUploadBelum_({ rows }, user));
    }
    case 'pelanggan_cari':
      return handlePelangganCari_({ q: body.q || '' }, user);
    case 'pelanggan_list_aktif':
      return handlePelangganListAktif_(user);
    case 'pelanggan_status':
      return requirePermission_(user, 'PELANGGAN_WRITE', () => handlePelangganStatus_(body, user));
    case 'pelanggan_import':
      return err_('Import massal pelanggan belum tersedia pada router API; tidak ada data yang diproses', 501);
    // ── SYNC ──────────────────────────────────────────────
    case 'sync_check' : return handleSyncCheck_(body);
    case 'sync_pull'  : return handleSyncPull_(body, user);
    case 'sync_push'  : return handleSyncPush_(body, user);

    // ── WILAYAH ───────────────────────────────────────────
    case 'wilayah_toggle_kabupaten':
      return requirePermission_(user, 'MASTER_WILAYAH_TOGGLE',
        () => handleWilayahToggle_(body));

    // ── JARINGAN FO ───────────────────────────────────────
    case 'server_create':
      return requirePermission_(user, 'JARINGAN_WRITE',
        () => handleServerCreate_(body, user));
    case 'olt_create':
      return requirePermission_(user, 'JARINGAN_WRITE',
        () => handleOltCreate_(body, user));
    case 'odc_create':
      return requirePermission_(user, 'JARINGAN_WRITE',
        () => handleOdcCreate_(body, user));
    case 'odp_create':
      return requirePermission_(user, 'JARINGAN_WRITE',
        () => handleOdpCreate_(body, user));

    // ── SDM ───────────────────────────────────────────────
    case 'karyawan_create':
      return requirePermission_(user, 'SDM_WRITE',
        () => handleKaryawanCreate_(body, user));
    case 'user_create':
      return requirePermission_(user, 'USER_CREATE',
        () => handleUserCreate_(body, user));

    // ── PELANGGAN ─────────────────────────────────────────
    case 'calon_create':
      return requirePermission_(user, 'CALON_CREATE',
        () => handleCalonCreate_(body, user));
    case 'calon_update_status':
      return requirePermission_(user, 'CALON_UPDATE',
        () => handleCalonUpdateStatus_(body, user));
    case 'pemasangan_create':
      return requirePermission_(user, 'PEMASANGAN_CREATE',
        () => handlePemasanganCreate_(body, user));
    case 'pemasangan_selesai':
      return requirePermission_(user, 'PEMASANGAN_SELESAI',
        () => handlePemasanganSelesai_(body, user));
    case 'pelanggan_ganti_jalur':
      return requirePermission_(user, 'PELANGGAN_WRITE',
        () => handleGantiJalur_(body, user));

    // ── INVENTORI ─────────────────────────────────────────
    case 'modem_create':
      return requirePermission_(user, 'INVENTORI_WRITE',
        () => handleModemCreate_(body, user));
    case 'modem_assign':
      return requirePermission_(user, 'INVENTORI_WRITE',
        () => handleModemAssign_(body, user));
    case 'stok_masuk':
      return requirePermission_(user, 'INVENTORI_WRITE',
        () => handleStokMasuk_(body, user));
    case 'stok_keluar':
      return requirePermission_(user, 'INVENTORI_WRITE',
        () => handleStokKeluar_(body, user));

    // ── KEUANGAN ──────────────────────────────────────────
    case 'pembayaran_create':
      return requirePermission_(user, 'KEUANGAN_WRITE',
        () => handlePembayaranCreate_(body, user));
    case 'setoran_create':
      return requirePermission_(user, 'KEUANGAN_WRITE',
        () => handleSetoranCreate_(body, user));
    case 'setoran_konfirmasi':
      return requirePermission_(user, 'KASIR_KONFIRMASI',
        () => handleSetoranKonfirmasi_(body, user));
    case 'tagihan_generate':
      return requirePermission_(user, 'KEUANGAN_WRITE',
        () => handleTagihanGenerate_(body, user));

    // ── UPLOAD FOTO ───────────────────────────────────────
    case 'foto_upload':
      return requirePermission_(user, 'FOTO_UPLOAD',
        () => handleFotoUpload_(body, user));

    // ciot
        case 'ciot_kirim_ringkasan':
      return requirePermission_(user, 'INVENTORI_WRITE',
        () => handleCiotKirimRingkasan_(body, user));

    case 'ciot_log_only':
      return requirePermission_(user, 'INVENTORI_WRITE',
        () => handleCiotLogOnly_(body, user));

    case 'dashboard_summary':
      return handleDashboardSummary_(user);

    default:
      return err_('Action tidak dikenal: ' + action);
  }
}

// ── Permission guard ───────────────────────────────────────
function requirePermission_(user, kode, fn) {
  if (!user.permissions || !user.permissions.includes(kode)) {
    return err_('Tidak punya izin: ' + kode, 403);
  }
  return fn();
}

// ══════════════════════════════════════════════════════════
// AUTH
// ══════════════════════════════════════════════════════════
function handleLogin_(body) {
  const { username, password } = body;
  if (!username || !password) return err_('Username/password kosong');

  const ss = getSS_('SDM');
  const users = ss.getSheetByName('MASTER_USER').getDataRange().getValues();
  const header = users[0];
  const uIdx   = header.indexOf('username');
  const pIdx   = header.indexOf('password_hash');
  const sIdx   = header.indexOf('salt');
  const rIdx   = header.indexOf('id_role');
  const idIdx  = header.indexOf('id_user');
  const stIdx  = header.indexOf('status');

  for (let i = 1; i < users.length; i++) {
    const row = users[i];
    if (row[uIdx] !== username) continue;
    if (row[stIdx] !== 'AKTIF') return err_('Akun tidak aktif');

    const salt = row[sIdx];
    const hash = Utilities.base64Encode(
      Utilities.computeDigest(
        Utilities.DigestAlgorithm.SHA_256,
        password + salt
      )
    );
    if (hash !== row[pIdx]) return err_('Password salah');

    // Ambil permissions dari role
    const idRole = row[rIdx];
    const perms  = getPermissionsForRole_(ss, idRole);

    // Update last_login
    const lastIdx = header.indexOf('last_login');
    ss.getSheetByName('MASTER_USER')
      .getRange(i + 1, lastIdx + 1).setValue(new Date().toISOString());

    const token = makeToken_(row[idIdx], idRole, perms);
    return ok_({ token, user_id: row[idIdx], role: idRole, permissions: perms });
  }
  return err_('Username tidak ditemukan');
}

function getPermissionsForRole_(ss, idRole) {
  const rp   = ss.getSheetByName('MASTER_ROLE_PERMISSION').getDataRange().getValues();
  const hdr  = rp[0];
  const rIdx = hdr.indexOf('id_role');
  const pIdx = hdr.indexOf('id_permission');
  const ids  = rp.slice(1).filter(r => r[rIdx] === idRole).map(r => r[pIdx]);

  const pm   = ss.getSheetByName('MASTER_PERMISSION').getDataRange().getValues();
  const ph   = pm[0];
  const piIdx= ph.indexOf('id_permission') === -1
             ? ph.indexOf('id_permission') : ph.indexOf('id_permission');
  const pkIdx= ph.indexOf('kode');
  const idColIdx = ph.findIndex(h => h === 'id_permission');

  return pm.slice(1)
    .filter(r => ids.includes(r[idColIdx]))
    .map(r => r[pkIdx]);
}

// ══════════════════════════════════════════════════════════
// SYNC
// ══════════════════════════════════════════════════════════

// Map master name → spreadsheet key
const MASTER_SS_MAP = {
  'MASTER_WILAYAH'              : 'WILAYAH',
  'MASTER_SUB_WILAYAH'          : 'WILAYAH',
  'MASTER_SERVER'               : 'JARINGAN',
  'MASTER_OLT'                  : 'JARINGAN',
  'MASTER_ODC'                  : 'JARINGAN',
  'MASTER_ODP'                  : 'JARINGAN',
  'MASTER_PORT_ODP'             : 'JARINGAN',
  'MASTER_SPLITTER'             : 'JARINGAN',
  'MASTER_KABEL'                : 'JARINGAN',
  'MASTER_KARYAWAN'             : 'SDM',
  'MASTER_TEKNISI'              : 'SDM',
  'MASTER_USER'                 : 'SDM',
  'MASTER_ROLE'                 : 'SDM',
  'MASTER_PERMISSION'           : 'SDM',
  'MASTER_PAKET'                : 'PELANGGAN',
  'MASTER_STATUS_PROSES'        : 'PELANGGAN',
  'MASTER_SUMBER_PELANGGAN'     : 'PELANGGAN',
  'MASTER_JENIS_PEMASANGAN'     : 'PELANGGAN',
  'TRANSAKSI_CALON_PELANGGAN'   : 'PELANGGAN',
  'TRANSAKSI_PEMASANGAN'        : 'PELANGGAN',
  'PELANGGAN'                   : 'PELANGGAN',
  'MASTER_MODEM'                : 'INVENTORI',
  'MASTER_MATERIAL'             : 'INVENTORI',
  'STOK_SALDO'                  : 'INVENTORI',
  'MASTER_JENIS_TRANSAKSI'      : 'KEUANGAN',
  'TAGIHAN'                     : 'KEUANGAN',
  'PEMBAYARAN'                  : 'KEUANGAN',
};

function handleSyncCheck_(body) {
  const { local_versions } = body; // { MASTER_WILAYAH: 3, ... }
  const updates = {};

  Object.entries(local_versions || {}).forEach(([masterName, localVer]) => {
    const ssKey = MASTER_SS_MAP[masterName];
    if (!ssKey) return;
    const sc   = getSS_(ssKey).getSheetByName('SYNC_CONTROL');
    if (!sc) return;
    const data = sc.getDataRange().getValues();
    const hdr  = data[0];
    const nIdx = hdr.indexOf('master_name');
    const vIdx = hdr.indexOf('version');
    for (let i = 1; i < data.length; i++) {
      if (data[i][nIdx] === masterName && data[i][vIdx] > localVer) {
        updates[masterName] = data[i][vIdx];
      }
    }
  });

  return ok_({ updates }); // {} = semua up to date
}

function handleSyncPull_(body, user) {
  const { master_name, since_version } = body;
  if (master_name === 'MASTER_USER' && !(user && user.permissions && user.permissions.includes('USER_CREATE'))) return err_('Tidak punya izin untuk membaca daftar pengguna', 403);
  const ssKey = MASTER_SS_MAP[master_name];
  if (!ssKey) return err_('Master tidak dikenal: ' + master_name);

  const sheet = getSS_(ssKey).getSheetByName(master_name);
  if (!sheet) return err_('Sheet tidak ditemukan: ' + master_name);

  const data   = sheet.getDataRange().getValues();
  const header = data[0];
  const vIdx   = header.indexOf('version');

  const rows = data.slice(1)
    .filter(r => vIdx < 0 || r[vIdx] > (since_version || 0))
    .map(r => {
      const obj = {};
            header.forEach((h, i) => {
        const field = String(h).toLowerCase();
        if (['password_hash', 'salt', 'password', 'token', 'api_secret'].includes(field)) return;
        obj[h] = r[i];
      });
      return obj;
    });

  return ok_({ master_name, rows, total: rows.length });
}

function handleSyncPush_(body, user) {
  const { transactions } = body;
  if (!Array.isArray(transactions)) return err_('transactions harus array');
  if (transactions.length > 100) return err_('Maksimal 100 transaksi per request', 413);

  const results = transactions.map(tx => {
    try {
      return routeTransaction_(tx, user);
    } catch(e) {
      return { local_id: tx && tx.local_id || null, ok: false, error: e.message };
    }
  });

  return ok_({ results });
}

// ── Router transaksi per entity_type ──────────────────────
function routeTransaction_(tx, user) {
  if (!tx || typeof tx !== 'object') return { local_id: null, ok: false, error: 'Transaksi tidak valid' };
  const { entity_type, payload, local_id } = tx;
  if (!payload || typeof payload !== 'object') return { local_id, ok: false, error: 'Payload tidak valid' };
  const required = {
    SUB_WILAYAH_CREATE: 'MASTER_WILAYAH_TOGGLE',
    CALON_CREATE: 'CALON_CREATE',
    CALON_UPDATE: 'CALON_UPDATE',
    CALON_UPDATE_STATUS: 'CALON_UPDATE',
    PEMASANGAN_CREATE: 'PEMASANGAN_CREATE',
    PEMASANGAN_SELESAI: 'PEMASANGAN_SELESAI',
    MODEM_CREATE: 'INVENTORI_WRITE',
    STOK_KELUAR: 'INVENTORI_WRITE',
    PEMBAYARAN_CREATE: 'KEUANGAN_WRITE',
  }[entity_type];
  if (!required) return { local_id, ok: false, error: 'entity_type tidak dikenal' };
  if (typeof local_id !== 'string' || !local_id.trim()) return { local_id, ok: false, error: 'local_id wajib diisi' };
  if (!user || !user.permissions || !user.permissions.includes(required)) return { local_id, ok: false, error: 'Tidak punya izin: ' + required };
  switch (entity_type) {
    case 'SUB_WILAYAH_CREATE': return txSubWilayahCreate_(payload, user, local_id);
    case 'CALON_CREATE': return txCalonCreate_(payload, user, local_id);
    case 'CALON_UPDATE': return txCalonUpdate_(payload, user, local_id);
    case 'CALON_UPDATE_STATUS': return txCalonUpdateStatus_(payload, user, local_id);
    case 'PEMASANGAN_CREATE': return txPemasanganCreate_(payload, user, local_id);
    case 'PEMASANGAN_SELESAI': return txPemasanganSelesai_(payload, user, local_id);
    case 'MODEM_CREATE': return txModemCreate_(payload, user, local_id);
    case 'STOK_KELUAR': return txStokKeluar_(payload, user, local_id);
    case 'PEMBAYARAN_CREATE': return txPembayaranCreate_(payload, user, local_id);
    default: return { local_id, ok: false, error: 'entity_type tidak dikenal' };
  }
}
// ══════════════════════════════════════════════════════════
// WILAYAH
// ══════════════════════════════════════════════════════════
function handleWilayahToggle_(body) {
  const { id_wilayah, status } = body;
  if (!['AKTIF','NONAKTIF'].includes(status))
    return err_('Status harus AKTIF atau NONAKTIF');

  const sheet = getSS_('WILAYAH').getSheetByName('MASTER_WILAYAH');
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];
  const idIdx = hdr.indexOf('id_wilayah');
  const stIdx = hdr.indexOf('status');
  const upIdx = hdr.indexOf('updated_at');

  for (let i = 1; i < data.length; i++) {
    if (data[i][idIdx] === id_wilayah) {
      sheet.getRange(i+1, stIdx+1).setValue(status);
      sheet.getRange(i+1, upIdx+1).setValue(now_());
      bumpSync_(getSS_('WILAYAH'), 'MASTER_WILAYAH');
      return ok_({ id_wilayah, status });
    }
  }
  return err_('Wilayah tidak ditemukan');
}

function txSubWilayahCreate_(payload, user, local_id) {
  const ss    = getSS_('WILAYAH');
  const sheet = ss.getSheetByName('MASTER_SUB_WILAYAH');
  const data  = sheet.getDataRange().getValues();

  // Cek idempotency
  const hdr     = data[0];
  const lidIdx  = hdr.indexOf('local_id');
  if (lidIdx >= 0 && data.slice(1).some(r => r[lidIdx] === local_id))
    return { local_id, ok: true, duplicate: true };

  // Cek kemiripan
  const namaIdx = hdr.indexOf('nama');
  const desaIdx = hdr.indexOf('id_desa');
  const normInput = payload.nama.toLowerCase().trim().replace(/\s+/g,' ');
  let flag = 'OK';

  data.slice(1).forEach(r => {
    if (r[desaIdx] !== payload.id_desa) return;
    const norm = String(r[namaIdx]).toLowerCase().trim().replace(/\s+/g,' ');
    if (levenshteinSimilarity_(normInput, norm) >= 0.75) flag = 'NEEDS_REVIEW';
  });

  const id  = uuid_();
  const now = now_();
  sheet.appendRow([id, payload.nama, payload.id_desa, flag,
    'AKTIF', 1, now, now, user.sub]);
  bumpSync_(ss, 'MASTER_SUB_WILAYAH');

  if (flag === 'NEEDS_REVIEW') notifyReviewData_({
    jenis: 'Sub-Wilayah Mirip', nama: payload.nama,
    id_desa: payload.id_desa, oleh: user.sub
  });

  return { local_id, ok: true, id_sub_wilayah: id, flag_review: flag };
}

// ══════════════════════════════════════════════════════════
// CALON PELANGGAN
// ══════════════════════════════════════════════════════════
function txCalonCreate_(payload, user, local_id) {
  const ss    = getSS_('PELANGGAN');
  const sheet = ss.getSheetByName('TRANSAKSI_CALON_PELANGGAN');

  // Idempotency
  const data = sheet.getDataRange().getValues();
  const hdr  = data[0];
  const lidIdx = hdr.indexOf('local_id');
  if (lidIdx >= 0 && data.slice(1).some(r => r[lidIdx] === local_id))
    return { local_id, ok: true, duplicate: true };

  const id  = uuid_();
  const now = now_();
  sheet.appendRow([
    id,
    payload.nama_ktp        || '',
    payload.no_hp           || '',
    payload.nik             || '',
    payload.id_desa         || '',
    payload.id_sub_wilayah  || '',
    payload.alamat_detail   || '',
    payload.id_paket        || '',
    payload.id_sumber       || '',
    'BARU',                         // status awal selalu BARU
    payload.url_foto_ktp    || '',
    payload.catatan         || '',
    'OK',                           // flag_review
    'AKTIF', 1, now, now,
    user.sub,
    local_id
  ]);
  bumpSync_(ss, 'TRANSAKSI_CALON_PELANGGAN');

  // Notif Telegram → topik Pelanggan Baru
  notifyCalonBaru_({
    nama_ktp: payload.nama_ktp, no_hp: payload.no_hp,
    id_paket: payload.id_paket, id_desa: payload.id_desa,
    oleh: user.sub
  });

  return { local_id, ok: true, id_calon: id };
}

function txCalonUpdate_(payload, user, local_id) {
  if (!payload.id_calon) return { local_id, ok: false, error: 'id_calon wajib diisi' };
  const ss = getSS_('PELANGGAN');
  const sheet = ss.getSheetByName('TRANSAKSI_CALON_PELANGGAN');
  const data = sheet.getDataRange().getValues();
  const hdr = data[0];
  const idIdx = hdr.indexOf('id_calon');
  const rowIndex = data.slice(1).findIndex(r => r[idIdx] === payload.id_calon);
  if (idIdx < 0 || rowIndex < 0) return { local_id, ok: false, error: 'Calon tidak ditemukan' };
  const rowNumber = rowIndex + 2;
  let changed = false;
  ['nama_ktp', 'no_hp', 'catatan', 'id_paket'].forEach(field => {
    const col = hdr.indexOf(field);
    if (col >= 0 && payload[field] !== undefined) {
      sheet.getRange(rowNumber, col + 1).setValue(payload[field]);
      changed = true;
    }
  });
  if (!changed) return { local_id, ok: true, unchanged: true };
  const updatedIdx = hdr.indexOf('updated_at');
  if (updatedIdx >= 0) sheet.getRange(rowNumber, updatedIdx + 1).setValue(now_());
  const versionIdx = hdr.indexOf('version');
  if (versionIdx >= 0) sheet.getRange(rowNumber, versionIdx + 1).setValue(Number(data[rowIndex + 1][versionIdx] || 0) + 1);
  bumpSync_(ss, 'TRANSAKSI_CALON_PELANGGAN');
  return { local_id, ok: true };
}

function txCalonUpdateStatus_(payload, user, local_id) {
  const sheet = getSS_('PELANGGAN').getSheetByName('TRANSAKSI_CALON_PELANGGAN');
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];
  const idIdx = hdr.indexOf('id_calon');
  const stIdx = hdr.indexOf('id_status_proses');
  const upIdx = hdr.indexOf('updated_at');
  const vIdx  = hdr.indexOf('version');

  for (let i = 1; i < data.length; i++) {
    if (data[i][idIdx] !== payload.id_calon) continue;
    sheet.getRange(i+1, stIdx+1).setValue(payload.status_baru);
    sheet.getRange(i+1, upIdx+1).setValue(now_());
    sheet.getRange(i+1, vIdx+1).setValue(Number(data[i][vIdx]) + 1);
    bumpSync_(getSS_('PELANGGAN'), 'TRANSAKSI_CALON_PELANGGAN');
    return { local_id, ok: true };
  }
  return { local_id, ok: false, error: 'Calon tidak ditemukan' };
}

// ══════════════════════════════════════════════════════════
// PEMASANGAN
// ══════════════════════════════════════════════════════════
function txPemasanganCreate_(payload, user, local_id) {
  const ss    = getSS_('PELANGGAN');
  const sheet = ss.getSheetByName('TRANSAKSI_PEMASANGAN');

  const data   = sheet.getDataRange().getValues();
  const lidIdx = data[0].indexOf('local_id');
  if (lidIdx >= 0 && data.slice(1).some(r => r[lidIdx] === local_id))
    return { local_id, ok: true, duplicate: true };

  const id  = uuid_();
  const now = now_();
  sheet.appendRow([
    id,
    payload.id_calon            || '',
    payload.id_teknisi_list     || '',  // JSON array string
    payload.id_jenis_pemasangan || '',
    payload.id_server           || '',
    payload.id_port             || '',
    '',                                  // id_modem — diisi saat selesai
    payload.tanggal_jadwal      || '',
    '',                                  // tanggal_selesai
    '',                                  // durasi_menit
    '', '', '',                          // opm, foto_ont, foto_opm
    '', '', '',                          // ssid, pass, ssid_5g
    '', '', '',                          // pass_default, sn, mac
    payload.catatan             || '',
    'MENUNGGU',
    'AKTIF', 1, now, now,
    user.sub, local_id
  ]);

  // Update status calon → PROSES_PASANG
  txCalonUpdateStatus_(
    { id_calon: payload.id_calon, status_baru: 'PROSES_PASANG' },
    user, null
  );

  // Kunci port jika dipilih
  if (payload.id_port) setPortStatus_(payload.id_port, 'DIPESAN', null);

  bumpSync_(ss, 'TRANSAKSI_PEMASANGAN');

  // Notif Telegram → topik Teknis & Pemasangan
  notifyPemasanganDijadwalkan_({
    id_calon: payload.id_calon,
    tanggal: payload.tanggal_jadwal,
    id_teknisi_list: payload.id_teknisi_list,
    oleh: user.sub
  });

  return { local_id, ok: true, id_pemasangan: id };
}

function txPemasanganSelesai_(payload, user, local_id) {
  const ssPel = getSS_('PELANGGAN');
  const sheet = ssPel.getSheetByName('TRANSAKSI_PEMASANGAN');
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];

  const idIdx = hdr.indexOf('id_pemasangan');
  const row   = data.slice(1).find(r => r[idIdx] === payload.id_pemasangan);
  if (!row) return { local_id, ok: false, error: 'Pemasangan tidak ditemukan' };

  const rowNum = data.findIndex(r => r[idIdx] === payload.id_pemasangan) + 1;
  const now    = now_();

  // Update kolom pemasangan
  const set = (col, val) => {
    const idx = hdr.indexOf(col);
    if (idx >= 0) sheet.getRange(rowNum, idx+1).setValue(val);
  };
  set('tanggal_selesai',      now);
  set('durasi_menit',         payload.durasi_menit     || '');
  set('nilai_opm_dbm',        payload.nilai_opm_dbm    || '');
  set('url_foto_ont',         payload.url_foto_ont     || '');
  set('url_foto_opm',         payload.url_foto_opm     || '');
  set('ssid_wifi',            payload.ssid_wifi        || '');
  set('password_wifi',        payload.password_wifi    || '');
  set('ssid_wifi_5g',         payload.ssid_wifi_5g     || '');
  set('password_wifi_default',payload.password_wifi_default || '');
  set('sn_modem',             payload.sn_modem         || '');
  set('mac_modem',            payload.mac_modem        || '');
  set('id_modem',             payload.id_modem         || '');
  set('catatan_teknisi',      payload.catatan_teknisi  || '');
  set('id_status_proses',     'SELESAI');
  set('updated_at',           now);
  set('version', Number(row[hdr.indexOf('version')]) + 1);

  // Aktifkan port
  if (payload.id_port || row[hdr.indexOf('id_port')]) {
    const portId = payload.id_port || row[hdr.indexOf('id_port')];
    setPortStatus_(portId, 'TERPAKAI', null); // id_pelanggan diisi setelah buat
  }

  // Buat record PELANGGAN
  const idPelanggan = createPelangganRecord_(row, hdr, payload, user, ssPel);

  // Link port ke pelanggan
  const portId = payload.id_port || row[hdr.indexOf('id_port')];
  if (portId) setPortStatus_(portId, 'TERPAKAI', idPelanggan);

  // Update status calon → TERPASANG
  txCalonUpdateStatus_(
    { id_calon: row[hdr.indexOf('id_calon')], status_baru: 'TERPASANG' },
    user, null
  );

  bumpSync_(ssPel, 'TRANSAKSI_PEMASANGAN');
  bumpSync_(ssPel, 'PELANGGAN');

  // Notif Telegram lengkap
  notifyPemasanganSelesai_({ ...payload, id_pelanggan: idPelanggan, oleh: user.sub });

  return { local_id, ok: true, id_pelanggan: idPelanggan };
}

// ── Buat record PELANGGAN dari data pemasangan ─────────────
function createPelangganRecord_(pemasRow, pemasHdr, payload, user, ssPel) {
  const get = col => {
    const i = pemasHdr.indexOf(col);
    return i >= 0 ? pemasRow[i] : '';
  };

  // Ambil data calon
  const idCalon  = get('id_calon');
  const ssCalonSheet = ssPel.getSheetByName('TRANSAKSI_CALON_PELANGGAN');
  const calonData    = ssCalonSheet.getDataRange().getValues();
  const calonHdr     = calonData[0];
  const calonRow     = calonData.slice(1)
    .find(r => r[calonHdr.indexOf('id_calon')] === idCalon) || [];
  const cGet = col => {
    const i = calonHdr.indexOf(col);
    return i >= 0 ? calonRow[i] : '';
  };

  const id  = uuid_();
  const now = now_();

  // Generate username PPPoE (butuh nomor urut dari counter)
  const username = generateUsernamePPPoE_(
    cGet('nama_ktp'), cGet('id_desa'), get('id_server'), ssPel
  );

  ssPel.getSheetByName('PELANGGAN').appendRow([
    id, username, idCalon, get('id_pemasangan'),
    cGet('nama_ktp'), cGet('no_hp'), cGet('nik'),
    cGet('id_desa'), cGet('id_sub_wilayah'), cGet('alamat_detail'),
    cGet('id_paket'), get('id_server'),
    payload.id_port || get('id_port'),
    payload.id_modem || '',
    payload.ssid_wifi || '', payload.password_wifi || '',
    payload.ssid_wifi_5g || '',
    payload.nilai_opm_dbm || '',
    cGet('url_foto_ktp'),
    payload.url_foto_ont || '',
    payload.url_foto_opm || '',
    now, '', 'AKTIF', 1, now, now
  ]);

  return id;
}

// ── Generate username PPPoE ────────────────────────────────
function generateUsernamePPPoE_(namaKtp, idDesa, idServer, ssPel) {
  // Ambil nomor urut berikutnya dari counter sheet
  const ss     = getSS_('PELANGGAN');
  let counter  = ss.getSheetByName('PELANGGAN');
  const total  = Math.max(counter.getLastRow() - 1, 0);
  const urut   = String(total + 1).padStart(4, '0');

  const nama   = namaKtp.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/[^a-z]/g, '');

  // Ambil nama desa dari WILAYAH
  const desaSheet = getSS_('WILAYAH').getSheetByName('MASTER_WILAYAH');
  const desaData  = desaSheet.getDataRange().getValues();
  const desaHdr   = desaData[0];
  const desaRow   = desaData.slice(1)
    .find(r => r[desaHdr.indexOf('id_wilayah')] === idDesa);
  const namaDesa  = desaRow
    ? desaRow[desaHdr.indexOf('nama')].toLowerCase().replace(/[^a-z]/g,'')
    : 'unknown';

  // Ambil suffix server dari JARINGAN
  const srvSheet = getSS_('JARINGAN').getSheetByName('MASTER_SERVER');
  const srvData  = srvSheet.getDataRange().getValues();
  const srvHdr   = srvData[0];
  const srvRow   = srvData.slice(1)
    .find(r => r[srvHdr.indexOf('id_server')] === idServer);
  const suffix   = srvRow
    ? srvRow[srvHdr.indexOf('suffix')]
    : '@ogoamas';

  return `${urut}${nama}.${namaDesa}${suffix}`;
}

// ── Set status port ODP ────────────────────────────────────
function setPortStatus_(idPort, status, idPelanggan) {
  const sheet = getSS_('JARINGAN').getSheetByName('MASTER_PORT_ODP');
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];
  const idIdx = hdr.indexOf('id_port');
  const stIdx = hdr.indexOf('status');
  const plIdx = hdr.indexOf('id_pelanggan');
  const upIdx = hdr.indexOf('updated_at');

  for (let i = 1; i < data.length; i++) {
    if (data[i][idIdx] !== idPort) continue;
    sheet.getRange(i+1, stIdx+1).setValue(status);
    if (plIdx >= 0) sheet.getRange(i+1, plIdx+1).setValue(idPelanggan || '');
    if (upIdx >= 0) sheet.getRange(i+1, upIdx+1).setValue(now_());
    return;
  }
}

// ══════════════════════════════════════════════════════════
// KEUANGAN
// ══════════════════════════════════════════════════════════
function txPembayaranCreate_(payload, user, local_id) {
  const ss = getSS_('KEUANGAN');
  const sheet = ss.getSheetByName('PEMBAYARAN');
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let id, now;
  try {
    const data = sheet.getDataRange().getValues();
    const hdr = data[0] || [];
    const localIdx = hdr.indexOf('local_id');
    const idIdx = hdr.indexOf('id_pembayaran');
    if (localIdx >= 0) {
      const duplicate = data.slice(1).find(r => String(r[localIdx]) === String(local_id));
      if (duplicate) return { local_id, ok: true, duplicate: true, id_pembayaran: idIdx >= 0 ? duplicate[idIdx] : '' };
    }
    id = uuid_();
    now = now_();
    sheet.appendRow([
      id,
      payload.id_tagihan || '',
      payload.id_pelanggan || '',
      payload.id_jenis_transaksi || '',
      payload.nominal || 0,
      payload.metode_bayar || 'CASH',
      user.sub,
      now,
      '', '',
      'MENUNGGU_KONFIRMASI',
      payload.catatan || '',
      1, now, now, local_id
    ]);
    bumpSync_(ss, 'PEMBAYARAN');
  } finally {
    lock.releaseLock();
  }
  notifyPembayaranMasuk_({
    id_pelanggan: payload.id_pelanggan,
    nominal: payload.nominal,
    jenis: payload.id_jenis_transaksi,
    staf: user.sub
  });
  return { local_id, ok: true, id_pembayaran: id };
}

function handleSetoranKonfirmasi_(body, user) {
  const { id_setoran } = body;
  const ss    = getSS_('KEUANGAN');
  const sheet = ss.getSheetByName('SETORAN_KASIR');
  const data  = sheet.getDataRange().getValues();
  const hdr   = data[0];
  const idIdx = hdr.indexOf('id_setoran');
  const stIdx = hdr.indexOf('status');
  const ksIdx = hdr.indexOf('id_kasir');
  const tkIdx = hdr.indexOf('tanggal_konfirmasi');

  for (let i = 1; i < data.length; i++) {
    if (data[i][idIdx] !== id_setoran) continue;
    const now = now_();
    sheet.getRange(i+1, stIdx+1).setValue('TERKONFIRMASI');
    sheet.getRange(i+1, ksIdx+1).setValue(user.sub);
    sheet.getRange(i+1, tkIdx+1).setValue(now);
    bumpSync_(ss, 'SETORAN_KASIR');

    // Notif Telegram konfirmasi kasir
    notifySetoranDikonfirmasi_({
      id_setoran, kasir: user.sub, tgl: now
    });

    return ok_({ id_setoran, status: 'TERKONFIRMASI' });
  }
  return err_('Setoran tidak ditemukan');
}

function handlePelangganStatus_(body, user) {
  const id = body.id;
  const status = body.status;
  if (!id || !['AKTIF', 'ISTIRAHAT', 'NONAKTIF'].includes(status)) return err_('ID atau status tidak valid');
  const ss = getSS_('PELANGGAN');
  const targets = [
    { name: 'PELANGGAN', idField: 'id_pelanggan' },
    { name: 'TRANSAKSI_CALON_PELANGGAN', idField: 'id_calon' },
  ];
  for (const target of targets) {
    const sheet = ss.getSheetByName(target.name);
    if (!sheet) continue;
    const data = sheet.getDataRange().getValues();
    if (!data.length) continue;
    const hdr = data[0];
    const idIdx = hdr.indexOf(target.idField);
    const statusIdx = hdr.indexOf('status');
    if (idIdx < 0 || statusIdx < 0) continue;
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][idIdx]) !== String(id)) continue;
      sheet.getRange(i + 1, statusIdx + 1).setValue(status);
      const updatedIdx = hdr.indexOf('updated_at');
      if (updatedIdx >= 0) sheet.getRange(i + 1, updatedIdx + 1).setValue(now_());
      const versionIdx = hdr.indexOf('version');
      if (versionIdx >= 0) sheet.getRange(i + 1, versionIdx + 1).setValue(Number(data[i][versionIdx] || 0) + 1);
      bumpSync_(ss, target.name);
      return ok_({ id, status });
    }
  }
  return err_('Pelanggan tidak ditemukan');
}
// ── Levenshtein similarity (untuk cek kemiripan nama) ─────
function levenshteinSimilarity_(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({length:m+1}, (_,i) =>
    Array.from({length:n+1}, (_,j) => i === 0 ? j : j === 0 ? i : 0));
  for (let i=1;i<=m;i++) for (let j=1;j<=n;j++)
    dp[i][j] = a[i-1]===b[j-1]
      ? dp[i-1][j-1]
      : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
  return 1 - dp[m][n] / Math.max(m,n,1);
}

// ══════════════════════════════════════════════════════════
// FOTO UPLOAD → Google Drive
// ══════════════════════════════════════════════════════════
function handleFotoUpload_(body, user) {
  const { jenis, id_calon, nama_ktp, nama_desa, id_server,
          tgl_daftar, base64data, mime_type } = body;

  if (!['KTP', 'ONT', 'OPM'].includes(jenis)) return err_('Jenis foto tidak valid');
  if (!['image/jpeg', 'image/png'].includes(mime_type)) return err_('Format foto harus JPEG atau PNG', 415);
  if (typeof base64data !== 'string' || !base64data || base64data.length > 8 * 1024 * 1024)
    return err_('Ukuran foto tidak valid atau melebihi batas', 413);
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(base64data)) return err_('Data base64 foto tidak valid');
  let imageBytes;
  try { imageBytes = Utilities.base64Decode(base64data); }
  catch (_) { return err_('Data foto tidak dapat dibaca'); }
  if (!imageBytes.length || imageBytes.length > 6 * 1024 * 1024)
    return err_('Ukuran foto tidak valid atau melebihi batas', 413);

  // Ambil/buat folder
  const rootFolder  = DriveApp.getFolderById(getRequiredScriptProperty_('SS_GALLERY_FOLDER'));
  const tgl         = tgl_daftar
    ? tgl_daftar.slice(0,10).replace(/-/g,'_')
    : new Date().toISOString().slice(0,10).replace(/-/g,'_');

  // Ambil suffix server
  const srvSheet = getSS_('JARINGAN').getSheetByName('MASTER_SERVER');
  const srvData  = srvSheet.getDataRange().getValues();
  const srvHdr   = srvData[0];
  const srvRow   = srvData.slice(1)
    .find(r => r[srvHdr.indexOf('id_server')] === id_server);
  const namaServer = srvRow
    ? srvRow[srvHdr.indexOf('nama')]  // "Ogoamas" atau "Bangkir"
    : 'Ogoamas';

  // Level 1: /Ogoamas 2026_09_28/
  const folderL1Name = `${namaServer} ${tgl}`;
  const folderL1     = getOrCreateDriveFolder_(rootFolder, folderL1Name);

  // Nama bersih untuk folder pelanggan
  const namaClean = (nama_ktp || 'unknown')
    .toLowerCase().replace(/[^a-z0-9]/g,'_');
  const desaClean = (nama_desa || 'unknown')
    .toLowerCase().replace(/[^a-z0-9]/g,'_');

  // Nomor urut sementara (dari sheet PELANGGAN)
  const total = Math.max(getSS_('PELANGGAN')
    .getSheetByName('PELANGGAN').getLastRow() - 1, 0);
  const urut  = String(total + 1).padStart(4,'0');

  // Level 2: /0042_budisantoso_tambu/
  const folderL2Name = `${urut}_${namaClean}_${desaClean}`;
  const folderL2     = getOrCreateDriveFolder_(folderL1, folderL2Name);

  // Nama file: 0042_KTP.jpg
  const ext      = mime_type === 'image/png' ? 'png' : 'jpg';
  const fileName = `${urut}_${jenis}.${ext}`;

  // Decode base64 & simpan
  const blob    = Utilities.newBlob(
    imageBytes, mime_type, fileName
  );
  const file    = folderL2.createFile(blob);
  // Existing link-sharing is retained for compatibility; KTP/receipt privacy needs a separate authenticated-viewer flow.
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  const url     = `https://drive.google.com/uc?id=${file.getId()}`;

  return ok_({ jenis, url, file_name: fileName });
}

function getOrCreateDriveFolder_(parent, name) {
  const iter = parent.getFoldersByName(name);
  return iter.hasNext() ? iter.next() : parent.createFolder(name);
}

// ============================================================
// CIOT TOOL — Integrasi Termux → PNS.NET
// ============================================================

function handleCiotKirimRingkasan_(body, user) {
  const p = body.payload;
  if (!p) return err_('payload kosong');

  const ss  = getSS_('INVENTORI');
  const now = now_();

  // ── 1. Cari / update / buat MASTER_MODEM ─────────────────
  const modemSheet = ss.getSheetByName('MASTER_MODEM');
  const modemData  = modemSheet.getDataRange().getValues();
  const mHdr       = modemData[0];

  const col = name => mHdr.indexOf(name);
  let idModem  = null;
  let foundRow = -1;

  for (let i = 1; i < modemData.length; i++) {
    if (modemData[i][col('serial_number')] === p.serial_number) {
      foundRow = i + 1; idModem = modemData[i][col('id_modem')]; break;
    }
  }

  if (foundRow > 0) {
    // Update kolom teknis
    const setC = (name, val) => {
      const idx = col(name);
      if (idx >= 0 && val !== undefined && val !== '' && val !== null)
        modemSheet.getRange(foundRow, idx + 1).setValue(val);
    };
    setC('mac_address',         p.mac_address);
    setC('wan_username',        p.wan_username);
    setC('ssid_wifi',           p.ssid_wifi);
    setC('max_client',          p.max_client);
    setC('pon_rx_power',        p.pon_rx_power);
    setC('ip_address',          p.ip_address);
    setC('last_config_at',      now);
    setC('updated_at',          now);
    const vIdx = col('version');
    if (vIdx >= 0) {
      modemSheet.getRange(foundRow, vIdx + 1)
        .setValue(Number(modemData[foundRow - 1][vIdx] || 0) + 1);
    }
    Logger.log('CIOT: MASTER_MODEM updated, SN=' + p.serial_number);
  } else {
    // Buat row baru
    idModem = uuid_();
    // Bangun row sesuai urutan header yang ada
    const row = mHdr.map(h => {
      const map = {
        id_modem          : idModem,
        merk              : 'CIOT',
        model             : 'GM220-S XPON',
        serial_number     : p.serial_number     || '',
        mac_address       : p.mac_address       || '',
        id_pelanggan      : '',
        url_foto_ont      : '',
        password_wifi_default: (PropertiesService.getScriptProperties().getProperty('MODEM_WIFI_DEFAULT_PASSWORD') || ''),
        sn_from_ocr       : '',
        status            : 'SIAP_PAKAI',
        version           : 1,
        created_at        : now,
        updated_at        : now,
        created_by        : user.sub,
        ssid_wifi         : p.ssid_wifi         || '',
        max_client        : p.max_client         || '',
        wan_username      : p.wan_username       || '',
        pon_rx_power      : p.pon_rx_power       || '',
        ip_address        : p.ip_address         || '',
        last_config_at    : now,
      };
      return map[h] !== undefined ? map[h] : '';
    });
    modemSheet.appendRow(row);
    Logger.log('CIOT: MASTER_MODEM row baru, SN=' + p.serial_number);
  }

  bumpSync_(ss, 'MASTER_MODEM');

  // ── 2. Catat ke LOG_KONFIGURASI_MODEM ────────────────────
  const logSheet = ss.getSheetByName('LOG_KONFIGURASI_MODEM');
  const logId    = uuid_();
  if (logSheet) {
    logSheet.appendRow([
      logId,
      idModem,
      p.wan_username        || '',
      p.serial_number       || '',
      p.mac_address         || '',
      p.ip_address          || '',
      p.ssid_wifi           || '',
      p.max_client          || '',
      p.pon_rx_power        || '',
      p.wan_type            || 'PPPoE',
      p.wan_connection_name || '',
      p.firmware_info       || '',
      'KONFIGURASI',
      p.keterangan          || '',
      user.sub,
      now
    ]);
    bumpSync_(ss, 'LOG_KONFIGURASI_MODEM');
  }

  // ── 3. Link ke PELANGGAN via wan_username ─────────────────
  let linkedPelanggan = null;
  if (p.wan_username) {
    try {
      const ssPel    = getSS_('PELANGGAN');
      const pelSheet = ssPel.getSheetByName('PELANGGAN');
      const pelData  = pelSheet.getDataRange().getValues();
      const pH       = pelData[0];
      const upIdx    = pH.indexOf('username_pppoe');
      const nmIdx    = pH.indexOf('nama_ktp');
      const midIdx   = pH.indexOf('id_modem');

      for (let i = 1; i < pelData.length; i++) {
        if (pelData[i][upIdx] === p.wan_username) {
          linkedPelanggan = pelData[i][nmIdx];
          // Update id_modem di PELANGGAN jika kosong
          if (midIdx >= 0 && !pelData[i][midIdx] && idModem) {
            pelSheet.getRange(i + 1, midIdx + 1).setValue(idModem);
          }
          break;
        }
      }
    } catch(e) {
      Logger.log('CIOT: gagal link pelanggan — ' + e.message);
    }
  }

  // ── 4. Notif Telegram topik Teknis & Pemasangan ───────────
  try {
    const opmVal  = p.pon_rx_power ? p.pon_rx_power + ' dBm' : '-';
    const opmIcon = p.pon_rx_power
      ? (parseFloat(p.pon_rx_power) >= -15 ? '✅' : parseFloat(p.pon_rx_power) >= -25 ? '⚠️' : '🔴')
      : '—';
    const msg =
`📡 <b>LAPORAN TEKNIS MODEM</b>
──────────────────
🖥️ Model        : CIOT GM220-S XPON
🔢 Serial No.   : ${p.serial_number       || '-'}
🌐 MAC Address  : ${p.mac_address         || '-'}
──────────────────
📶 SSID WiFi    : ${p.ssid_wifi           || '-'}
👥 Max Client   : ${p.max_client          || '-'}
🔌 WAN Username : <b>${p.wan_username     || '-'}</b>
${opmIcon} Sinyal OPM   : ${opmVal}
🖥️ IP Address   : ${p.ip_address         || '-'}
──────────────────
${linkedPelanggan
  ? `👤 Pelanggan    : <b>${linkedPelanggan}</b>`
  : `⚠️ WAN username belum terdaftar di sistem`}
──────────────────
Dikirim         : ${user.sub || '-'}
🕐 ${now}`;
    ciotNotifTelegram_(msg);
  } catch(e) {
    Logger.log('CIOT notif TG gagal: ' + e.message);
  }

  return ok_({
    id_log   : logId,
    id_modem : idModem,
    linked   : !!linkedPelanggan,
    pelanggan: linkedPelanggan,
  });
}

// ── Log saja tanpa update MASTER_MODEM ───────────────────
function handleCiotLogOnly_(body, user) {
  const p        = body.payload || {};
  const ss       = getSS_('INVENTORI');
  const logSheet = ss.getSheetByName('LOG_KONFIGURASI_MODEM');

  if (!logSheet)
    return err_('LOG_KONFIGURASI_MODEM belum ada — jalankan updateSkemaModem() dulu');

  logSheet.appendRow([
    uuid_(), '',
    p.wan_username        || '',
    p.serial_number       || '',
    p.mac_address         || '',
    p.ip_address          || '',
    p.ssid_wifi           || '',
    p.max_client          || '',
    p.pon_rx_power        || '',
    p.wan_type            || 'PPPoE',
    p.wan_connection_name || '',
    p.firmware_info       || '',
    'CEK_STATUS',
    p.keterangan          || '',
    user.sub, now_()
  ]);
  bumpSync_(ss, 'LOG_KONFIGURASI_MODEM');
  return ok_({ logged: true });
}

// ── Helper notif Telegram khusus CIOT ────────────────────
function ciotNotifTelegram_(msg) {
  const props   = PropertiesService.getScriptProperties();
  const token   = props.getProperty('TG_BOT_TOKEN');
  const chatId  = props.getProperty('TG_CHAT_ID');
  const topicId = props.getProperty('TG_TOPIC_TEKNIS') || '8';
  if (!token || !chatId) {
    Logger.log('CIOT TG: BOT_TOKEN atau CHAT_ID belum dikonfigurasi');
    return;
  }
  UrlFetchApp.fetch(
    `https://api.telegram.org/bot${token}/sendMessage`,
    {
      method            : 'post',
      contentType       : 'application/json',
      payload           : JSON.stringify({
        chat_id              : chatId,
        text                 : msg,
        parse_mode           : 'HTML',
        message_thread_id    : topicId,
        disable_web_page_preview: true,
      }),
      muteHttpExceptions: true,
    }
  );
}

// ── Setup Telegram config dari Script Properties ──────────
function setupTelegramForCiot() {
  const props = PropertiesService.getScriptProperties();
  const missing = ['TG_BOT_TOKEN', 'TG_CHAT_ID'].filter(key => !props.getProperty(key));
  if (missing.length) throw new Error('Lengkapi Script Properties: ' + missing.join(', '));
  Logger.log('Konfigurasi Telegram CIOT siap; nilai tidak dicetak.');
}
