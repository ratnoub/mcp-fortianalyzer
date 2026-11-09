# mcp-fortianalyzer

Server [Model Context Protocol](https://modelcontextprotocol.io) (MCP) yang
mengekspos **FortiAnalyzer JSON-RPC API** sebagai tool MCP, dibangun di atas
[FastMCP](https://gofastmcp.com).

Server ini memberikan akses SOC / analisis log yang read-heavy dari klien MCP
(Claude Desktop, LM Studio, agen, dll.) ke perangkat FortiAnalyzer: pencarian
log, kueri FortiView, laporan, insiden, alert, rescan IoC, inventaris perangkat
DVM, pengambilan PCAP, dan lain-lain.

> Build ini sengaja menyertakan **semua tool read/query beserta operasi
> update/acknowledge, tetapi tidak menyertakan tool add/delete/create**
> (tambahan/hapus perangkat, tambahan/hapus perangkat massal, pembuatan
> komentar alert, dan pembuatan insiden dikecualikan).

## Konfigurasi

Konfigurasi dibaca dari file `config.yaml`. Secara default server mencarinya
dengan urutan:

1. Path pada variabel lingkungan `FAZ_CONFIG_FILE` (jika di-set).
2. `config.yaml` di direktori kerja saat ini.
3. `config.yaml` di root proyek.

Mulai dari template yang di-commit dan isi dengan nilai Anda sendiri:

```bash
cp config.example.yaml config.yaml
```

`config.yaml` di-gitignore (karena menyimpan rahasia). Contoh:

```yaml
config:
  fortianalyzer:
    host: 172.18.7.15
    api_key: <your-api-token>
    verify_ssl: false
    log_level: info
    default_adom: root
    auth_token: <your-http-auth-token>
```

Kunci opsional: `username`, `password`, `ca_bundle`, `timeout`, `max_retries`,
`log_file`, `log_format`, `auth_token`. Nilai apa pun dapat ditimpa dengan
variabel lingkungan (mis. `FORTIANALYZER_HOST`, `FORTIANALYZER_API_TOKEN`,
`FORTIANALYZER_VERIFY_SSL`, `DEFAULT_ADOM`, `LOG_LEVEL`, `FAZ_AUTH_TOKEN`).

`auth_token` (atau variabel lingkungan `FAZ_AUTH_TOKEN`) melindungi endpoint
HTTP. Jika tidak di-set, server menghasilkan token acak saat startup dan
menampilkannya (lihat [Autentikasi](#autentikasi)).

## Instalasi

Cara instalasi yang direkomendasikan adalah dengan [pipx](https://pipx.pypa.io/),
yang menginstal perintah `mcp-fortianalyzer` ke dalam lingkungan terisolasi:

```bash
# Instal pipx-nya dulu jika belum ada
python -m pip install --user pipx
python -m pipx ensurepath

# Instal proyek ini (dari clone repositori)
pipx install .

# atau langsung dari GitHub
pipx install "git+https://github.com/ratnoub/mcp-fortianalyzer.git"
```

`pipx install .` membangun paket dan mengekspos perintah `mcp-fortianalyzer` ke
`PATH` Anda. Untuk upgrade setelah menarik perubahan baru, jalankan ulang
`pipx install --force .`.

<details>
<summary>Alternatif: instalasi dengan pip biasa (mis. untuk pengembangan)</summary>

```bash
# Instalasi development (editable)
pip install -e ".[dev]"
```

</details>

## Menjalankan

**stdio** (untuk klien MCP lokal seperti Claude Desktop):

```bash
mcp-fortianalyzer --transport stdio
```

**HTTP** (default — untuk deployment tercontainer / jarak jauh):

```bash
mcp-fortianalyzer
```

Secara default server mendengarkan di **`0.0.0.0:5750`** dan menyajikan
endpoint MCP di **`http://<IP>:5750/mcp`**.

### Opsi baris perintah

| Flag | Default | Deskripsi |
|------|---------|-----------|
| `--transport {stdio,http}` | auto-detect | Transport yang digunakan. Jika tidak di-set, lingkungan TTY atau Docker menjalankan HTTP, stdin yang di-pipe menjalankan stdio. |
| `--host` | `0.0.0.0` | Alamat bind HTTP. |
| `--port` | `5750` | Port bind HTTP. |
| `--path` | `/mcp` | Path endpoint HTTP. |
| `--token` | — | Token autentikasi untuk mode HTTP (lihat [Autentikasi](#autentikasi)). |
| `--no-auth` | off | Nonaktifkan penegakan token autentikasi pada mode HTTP (tidak disarankan). |
| `--daemon` | off | Jalankan server HTTP di background lalu keluar. |

### Menjalankan sebagai daemon background

```bash
mcp-fortianalyzer --daemon --token "my-secret-token"
```

Perintah ini memunculkan proses background yang terdetach dan langsung
kembali, menampilkan PID, endpoint, file log, file PID, dan (jika token
dihasilkan) token-nya:

```
FortiAnalyzer MCP server started in the background (daemon mode).
  PID:        47324
  Endpoint:   http://0.0.0.0:5750/mcp
  Log file:   /path/to/mcp-fortianalyzer.log
  PID file:   /path/to/mcp-fortianalyzer.pid
  Auth token: my-secret-token
  Stop with:  taskkill /PID 47324
```

File log dan PID ditulis ke direktori saat ini (timpa dengan variabel
lingkungan `FAZ_DAEMON_DIR`). Hentikan daemon dengan perintah yang
ditampilkan (`taskkill /PID <pid>` di Windows, `kill <pid>` di Unix).

### Variabel lingkungan

`FAZ_TRANSPORT`, `FAZ_HTTP_HOST`, `FAZ_HTTP_PORT`, `FAZ_AUTH_TOKEN`,
`FAZ_CONFIG_FILE`, dan `FAZ_DAEMON_DIR` juga dihormati.

## Autentikasi

Mode HTTP dilindungi oleh bearer token. Token diselesaikan dengan urutan:

1. Flag baris perintah `--token`.
2. Variabel lingkungan `FAZ_AUTH_TOKEN`.
3. Kunci `auth_token` di `config.yaml`.
4. Token yang dihasilkan secara acak (ditampilkan ke konsol saat startup).

Klien mengirimkannya sebagai header standar `Authorization: Bearer <token>`.
Misalnya, dengan klien FastMCP:

```python
from fastmcp import Client

async with Client("http://<IP>:5750/mcp", auth="<token>") as c:
    tools = await c.list_tools()
```

Permintaan tanpa token valid ditolak dengan `401 Unauthorized`. Gunakan
`--no-auth` untuk menonaktifkan penegakan (tidak disarankan untuk apa pun
selain pengujian lokal).

## Mendaftarkan ke Claude Desktop

Tambahkan ke `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fortianalyzer": {
      "command": "mcp-fortianalyzer",
      "env": {
        "FAZ_CONFIG_FILE": "/absolute/path/to/config.yaml"
      }
    }
  }
}
```

## Tool

Server mendaftarkan **71 tool** di area-area berikut. Semuanya adalah operasi
read/query beserta langkah workflow update/acknowledge; tool add/delete/create
sengaja dikecualikan.

### Perangkat & VDOM (4)

| Tool | Deskripsi |
|------|-----------|
| `get_device_info` | Dapatkan informasi detail tentang perangkat tertentu. Mengambil konfigurasi dan status lengkap perangkat. |
| `list_device_groups` | Daftarkan semua grup perangkat dalam ADOM. Grup perangkat memungkinkan pengorganisasian perangkat untuk manajemen kebijakan dan log. |
| `list_device_vdoms` | Daftarkan VDOM untuk perangkat tertentu. Virtual Domain (VDOM) adalah instance virtual independen di dalam perangkat FortiGate. |
| `search_devices` | Cari perangkat dengan filter. |

### Event & Alert (8)

| Tool | Deskripsi |
|------|-----------|
| `acknowledge_alerts` | Akui satu atau lebih alert. Menandai alert sebagai sudah diakui untuk pelacakan workflow SOC. |
| `get_alert_count` | Dapatkan jumlah alert yang memenuhi kriteria. |
| `get_alert_details` | Dapatkan detail tambahan untuk alert. Mengambil informasi lanjutan tentang alert termasuk pemetaan MITRE ATT&CK dan konteks tambahan. |
| `get_alert_handlers` | Dapatkan definisi alert-handler (aturan deteksi) event. Membaca konfigurasi alert-handler: nama, id, dan aturan masing-masing handler (severity, filter, groupby, tags). Ini adalah katalog aturan deteksi yang dijalankan perangkat — blok bangunan read-only untuk skill ``alert_rules`` Wave-2. |
| `get_alert_incident_stats` | Dapatkan statistik alert dan insiden. Mengambil statistik agregat untuk dasbor SOC. Breakdown yang dikembalikan tetap -- ``timescale`` hanya memilih lebar bucket. Tool ini dulu menerima ``stat_type`` ("severity", "severity-timescale", "status"); endpoint tidak memiliki parameter seperti itu di 7.6.6 atau 8.0.0, jadi ia tidak pernah memilih apa pun: di live, nilai tak masuk akal dan "severity" mengembalikan respons byte-identik sementara tool memantulkan kembali tipe yang diminta seolah sudah diterapkan. |
| `get_alert_logs` | Dapatkan entri log yang terkait dengan alert. Mengambil event log asli yang memicu alert. |
| `get_alerts` | Dapatkan event alert dari FortiAnalyzer. Mengambil alert keamanan yang dihasilkan oleh event handler dan aturan korelasi. |
| `unacknowledge_alerts` | Batalkan pengakuan satu atau lebih alert. Menghapus status pengakuan dari alert. |

### FortiView (3)

| Tool | Deskripsi |
|------|-----------|
| `fetch_fortiview` | Ambil hasil kueri FortiView berdasarkan TID. Mengambil hasil dari kueri FortiView yang sebelumnya dimulai. |
| `get_fortiview_data` | Dapatkan data FortiView dengan penanganan TID otomatis. Fungsi praktis yang menjalankan kueri FortiView dan menunggu hasilnya. Menangani workflow TID dua langkah secara otomatis. |
| `run_fortiview` | Mulai kueri analitik FortiView. FortiView menyediakan visibilitas dan dasbor analitik real-time. Ini memulai kueri async dan mengembalikan TID untuk mengambil hasil. |

### Insiden (5)

| Tool | Deskripsi |
|------|-----------|
| `get_incident` | Dapatkan insiden tertentu berdasarkan ID. Mengambil informasi detail tentang satu insiden. |
| `get_incident_count` | Dapatkan jumlah insiden yang memenuhi kriteria. Jendela waktu diterapkan meskipun FortiAnalyzer tidak mendokumentasikannya pada endpoint ini — lihat ``get_incidents`` untuk ukurannya. |
| `get_incident_stats` | Dapatkan statistik insiden. Mengambil statistik agregat untuk dasbor SOC termasuk jumlah per severity, status, dan tren. |
| `get_incidents` | Dapatkan insiden keamanan dari FortiAnalyzer. Mengambil insiden dari modul manajemen insiden. Insiden dapat dibuat secara manual atau otomatis dari alert. Jendela waktu DITERAPKAN, meskipun FortiAnalyzer tidak mendokumentasikan ``time-range`` pada endpoint ini. Terverifikasi di 7.6.6: jendela yang mencakup createtime insiden mengembalikannya, jendela di 2000 dan 2099 tidak mengembalikan apa pun, dan penghilangan jendela mengembalikan semuanya — pola yang sama yang diberikan ``/incident/stats`` yang terdokumentasi. Setiap record juga membawa ``createtime`` dan ``lastupdate``. |
| `update_incident` | Perbarui insiden yang sudah ada. Memodifikasi properti insiden untuk manajemen workflow SOC. Tidak ada field penugasan/kepemilikan pada API ini. Tool ini dulu menerima ``assignee``; tidak ada field seperti itu di 7.6.6 atau 8.0.0, jadi ia dibuang oleh perangkat sementara panggilan melaporkan sukses. ``last_user`` mencatat siapa yang terakhir menyentuh record, yang merupakan field nyata terdekat -- itu adalah stempel audit, bukan penugasan. |

### IOC (Indicators of Compromise) (6)

| Tool | Deskripsi |
|------|-----------|
| `acknowledge_ioc_events` | Akui event IOC. Menandai event deteksi IOC sebagai sudah diakui untuk pelacakan SOC. Identifikasi masing-masing event seperti yang dilakukan perangkat -- dengan endpoint plus timestamp saat ia terpicu. Tool ini dulu menerima daftar ``ioc_ids`` dengan ``user``; baik event-id maupun field pengguna-pengakuan tidak ada di API IOC 7.6.6 atau 8.0.0, jadi keduanya tidak pernah sampai ke perangkat dalam bentuk yang dapat ditindaklanjuti. |
| `get_ioc_license_state` | Dapatkan status lisensi IOC. Memeriksa status dan kemampuan lisensi IOC saat ini. Deteksi IOC memerlukan lisensi FortiGuard IOC yang aktif. |
| `get_ioc_rescan_history` | Dapatkan riwayat rescan IOC. Mengambil riwayat operasi rescan IOC sebelumnya. |
| `get_ioc_rescan_status` | Dapatkan status rescan IOC. Memeriksa kemajuan operasi rescan IOC. |
| `run_and_wait_ioc_rescan` | Jalankan rescan IOC dan tunggu hingga selesai. Fungsi praktis yang memulai rescan IOC dan mem-poll hingga selesai. Menangani workflow TID secara otomatis. |
| `run_ioc_rescan` | Mulai rescan IOC. Memulai rescan log historis terhadap basis data IOC saat ini. Mengembalikan TID untuk melacak kemajuan rescan. |

### Log (10)

| Tool | Deskripsi |
|------|-----------|
| `cancel_log_search` | Lepaskan handle pagination (dan tugas FAZ jika masih hidup). Panggil ini ketika Anda selesai mem-paging hasil query_logs untuk membebaskan handle in-process. FortiAnalyzer memangkas tugas logsearch yang selesai dengan sendirinya, jadi pembatalan di sisi perangkat bersifat best-effort; pembersihan handle selalu berhasil. |
| `fetch_more_logs` | Ambil halaman lain dari pencarian query_logs sebelumnya menggunakan handle-nya. Karena tid logsearch FortiAnalyzer bersifat sekali-pakai, ini menjalankan ulang kueri yang sama (ADOM, logtype, filter, perangkat, dan jendela waktu yang sama) pada offset/limit yang diminta menggunakan parameter pencarian yang tercatat untuk `tid`. Anda biasanya hanya meneruskan tid/offset/limit. Jika handle tidak dikenal oleh proses server ini (kedaluwarsa atau dari proses lain), responsnya adalah error terstruktur dengan error="tid_invalid_or_expired" dan rekomendasi untuk menjalankan ulang query_logs. |
| `get_log_fields` | Dapatkan field log yang tersedia untuk suatu tipe log -- apa yang dapat Anda filter. Respons trafik live berjalan hingga sekitar 200 definisi di dua daftar, yang lebih dari konteks yang layak dibaca penuh. Teruskan ``name_filter`` untuk menyempitkannya ke field yang benar-benar Anda cari ("src", "port", "app"); hitungan di respons menyatakan berapa yang dibuang sehingga jawaban sempit tidak pernah disalahartikan sebagai seluruh katalog. |
| `get_log_search_progress` | Laporkan status handle pagination query_logs. query_logs menjalankan setiap pencarian secara sinkron (ia hanya kembali setelah halaman selesai), dan tugas logsearch FortiAnalyzer bersifat sekali-pakai dan dipangkas saat selesai. Jadi tidak ada tugas in-progress yang dapat di-poll secara terpisah: handle yang dikenal sudah selesai. Gunakan fetch_more_logs(tid=...) untuk mengambil halaman selanjutnya. |
| `get_log_stats` | Dapatkan statistik log untuk suatu ADOM. Mengembalikan statistik tentang penyimpanan log, laju, dan status logging perangkat. |
| `get_logfiles_state` | Dapatkan informasi status file log. Mendaftarkan file log yang tersedia di disk untuk perangkat/VDOM. |
| `search_archived_logs` | Cari record di dalam file log FortiAnalyzer yang diarsipkan. Gunakan `get_logfiles_state` untuk menemukan nama file. |
| `get_archived_log_data` | Baca rentang byte terbatas dari file log yang diarsipkan. |
| `get_pcap_file` | Dapatkan file PCAP yang terkait dengan entri log. Beberapa log (seperti IPS) menyertakan tangkapan paket terkait. Ini mengambil data file PCAP. |
| `query_logs` | Kueri log dari basis data log FortiAnalyzer. Ini mengimplementasikan workflow pencarian log berbasis TID dua langkah: 1. Mulai tugas pencarian (mengembalikan TID) 2. Poll untuk hasil hingga selesai |

### PCAP (5)

| Tool | Deskripsi |
|------|-----------|
| `download_pcap_by_url` | Unduh file PCAP menggunakan pcapurl dari hasil pencarian. Gunakan ini ketika Anda sudah memiliki pcapurl dari panggilan search_ips_logs sebelumnya. |
| `get_pcap_by_session` | Unduh file PCAP untuk ID sesi tertentu. Mencari entri log IPS berdasarkan ID sesi dan mengunduh file PCAP terkait jika tersedia. |
| `list_available_pcaps` | Daftarkan event IPS yang memiliki file PCAP tersedia. Cara cepat untuk melihat PCAP apa yang tersedia sebelum mengunduh. Mengembalikan ringkasan masing-masing event dengan ID sesi untuk unduhan tertarget. |
| `search_and_download_pcaps` | Cari event IPS dan unduh semua PCAP yang cocok. Fungsi praktis yang menggabungkan search_ips_logs dan unduhan PCAP menjadi satu operasi. Berguna untuk pengumpulan forensik massal. |
| `search_ips_logs` | Cari log IPS/serangan dengan filtering lanjutan. Cari event IPS (Intrusion Prevention System) di FortiAnalyzer dengan opsi filtering fleksibel. Mengembalikan entri log yang dapat digunakan untuk mengunduh file PCAP terkait. Ini adalah titik masuk yang tepat untuk pekerjaan IPS -- ia memfilter berdasarkan CVE dan ketersediaan PCAP, yang tidak bisa dilakukan query_logs(logtype="attack", filters=[...]). Perhatikan `tid` yang dikembalikan BUKAN handle pagination (lihat Returns); naikkan `limit` alih-alih mencoba mem-paging, dan teruskan has_pcap=True ketika tujuannya adalah unduhan PCAP. |

### Laporan (11)

| Tool | Deskripsi |
|------|-----------|
| `fetch_report` | Ambil status dan kemajuan laporan berdasarkan TID. Memeriksa kemajuan laporan yang sedang berjalan. |
| `get_report_data` | Unduh data laporan yang selesai. Mengambil konten laporan yang dihasilkan setelah selesai. Data laporan dikembalikan sebagai konten base64-encoded. |
| `get_report_history` | Dapatkan riwayat laporan - daftar laporan yang dihasilkan. Mengambil daftar laporan yang selesai/dihasilkan. |
| `get_running_reports` | Dapatkan laporan yang sedang berjalan saat ini. Memeriksa status laporan yang saat ini sedang dihasilkan. Gunakan ini setelah run_report() untuk memantau kemajuan. |
| `list_report_schedules` | Daftarkan jadwal laporan, opsional dibatasi pada satu layout. Read-only; tidak membuat jadwal yang hilang. |
| `get_report_schedule_details` | Dapatkan konfigurasi jadwal laporan, termasuk field periodenya. Read-only. |
| `list_report_layouts` | Daftarkan layout laporan yang tersedia di FortiAnalyzer. PENTING: Layout adalah laporan yang dapat dijalankan. Template adalah cetak biru read-only. Ketika pengguna meminta "menjalankan laporan", Anda perlu mencari layout, bukan template. Masing-masing layout memiliki layout-id yang diperlukan untuk menjalankan laporan. Jadwal harus ada untuk layout sebelum ia dapat dijalankan (dibuat otomatis). |
| `list_report_templates` | Daftarkan template laporan read-only yang tersedia di FortiAnalyzer. PENTING: Template adalah cetak biru yang dilindungi, bukan laporan yang dapat dijalankan. Untuk menjalankan laporan gunakan list_report_layouts() + run_report() alih-alih. Template biasanya di-clone menjadi layout kustom melalui GUI/CLI FortiAnalyzer. Mengembalikan template yang disajikan oleh endpoint FAZ khusus GET /report/adom/{adom}/template/list, yang berbeda dari endpoint layout yang digunakan list_report_layouts(). |
| `run_and_wait_report` | Jalankan laporan dan tunggu hingga selesai. PENTING: Ini menjalankan LAYOUT, bukan template. Gunakan list_report_layouts() untuk melihat laporan yang tersedia. Fungsi praktis yang: 1. Mencari layout-id berdasarkan judul 2. Memastikan jadwal ada 3. Menjalankan laporan 4. Mem-poll hingga selesai atau timeout |
| `run_report` | Jalankan laporan di FortiAnalyzer. PENTING: Ini menjalankan LAYOUT, bukan template. Template adalah cetak biru read-only. Gunakan list_report_layouts() untuk melihat laporan yang tersedia. Fungsi ini: 1. Mencari layout-id berdasarkan judul (atau menggunakan langsung jika numerik) 2. Memastikan jadwal ada untuk layout (membuat jika diperlukan) 3. Menjalankan laporan dan mengembalikan TID untuk pelacakan Laporan berjalan secara asinkron. Gunakan get_running_reports() untuk memeriksa kemajuan dan get_report_data() untuk mengunduh laporan yang selesai. |
| `save_report` | Unduh, ekstrak, dan simpan laporan yang selesai ke disk. FortiAnalyzer mengembalikan laporan sebagai file ZIP base64-encoded. Tool ini mengunduh laporan, mendekode, mengekstrak isinya, dan menyimpan file laporan ke direktori yang ditentukan. |

### SOAR (2)

| Tool | Deskripsi |
|------|-----------|
| `get_indicator_enrichment` | Dapatkan reputasi/enrichment IOC untuk suatu indikator. Mengembalikan reputasi tersimpan untuk IP, URL, atau domain: verdict (``enrichment-reputation`` = Good/Suspicious/Malicious/NoReputationAvailable), ``enrichment-confidence`` (0-100), status, dan UUID indikator/enrichment. Dengan detail_level "extended", juga melampirkan ``enrichment-detail`` mentah dari sumber reputasi. Hanya membaca enrichment yang ada — tidak memicu lookup baru. Memerlukan SOAR berlisensi dengan sumber reputasi yang telah memperkaya indikator. |
| `get_linked_indicators` | Dapatkan indikator IOC yang terkait dengan alert atau insiden. Mengembalikan indikator SOAR (IP/URL/Domain) yang terkait dengan alert atau insiden tertentu — titik masuk untuk memperkaya indikator yang benar-benar terlibat dalam deteksi. Memerlukan SOAR berlisensi di FAZ. |

### Sistem (11)

| Tool | Deskripsi |
|------|-----------|
| `get_adom` | Dapatkan informasi detail tentang ADOM tertentu. |
| `get_api_ratelimit` | Dapatkan konfigurasi rate limiting API saat ini. Mengembalikan rate limit yang dikonfigurasi untuk operasi baca dan tulis API. Fitur ini tersedia di FortiAnalyzer 7.6.5 dan seterusnya. Rate limiting membantu melindungi FortiAnalyzer dari penyalahgunaan API dengan membatasi jumlah permintaan yang dapat dilakukan per detik. |
| `get_device` | Dapatkan informasi detail tentang perangkat tertentu. |
| `get_ha_status` | Dapatkan status High Availability (HA) FortiAnalyzer. Mengembalikan status cluster HA termasuk: - Mode HA (standalone, cluster) - Anggota cluster dan statusnya - Status sinkronisasi - Peran primer/sekunder |
| `get_system_status` | Dapatkan status sistem dan informasi versi FortiAnalyzer. Mengembalikan status sistem komprehensif termasuk: - Versi dan build FortiAnalyzer - Hostname sistem - Nomor seri - Mode domain admin - Informasi platform - Uptime dan load |
| `get_task` | Dapatkan status detail tugas tertentu. |
| `list_adoms` | Daftarkan semua Administrative Domain (ADOM) di FortiAnalyzer. ADOM digunakan untuk mempartisi FortiAnalyzer menjadi domain manajemen terpisah, masing-masing dengan perangkat, log, dan konfigurasinya sendiri. Teruskan `fields` kecuali Anda benar-benar memerlukan objek lengkap. Default adalah setiap field yang didefinisikan perangkat -- sekitar 35 per ADOM, kebanyakan placeholder kosong (slot IPv6 DNS yang tidak terpakai, deskripsi kosong, tab_status, logview_customize). fields=["name", "state"] menjawab "ADOM apa yang ada dan apakah diaktifkan" untuk sepersekian dari respons. |
| `list_devices` | Daftarkan semua perangkat yang terdaftar dalam ADOM. FortiAnalyzer mengumpulkan log dari FortiGate dan perangkat Fortinet lainnya. Ini mendaftarkan semua perangkat yang dikonfigurasi untuk mengirim log ke ADOM ini. Teruskan `fields` kecuali Anda benar-benar memerlukan objek lengkap. Default adalah sekitar 60 field per perangkat, termasuk kunci kredensial yang dikembalikan sebagai placeholder "***REDACTED***" dan array nol mgmt.__data yang tidak terpakai. fields=["name", "ip", "os_ver", "platform_str"] mencakup sebagian besar pertanyaan inventaris; tambahkan "sn" untuk nomor seri, yang juga menjadi filter `device` di tempat lain pada server ini. |
| `list_tasks` | Daftarkan semua tugas di FortiAnalyzer. Tugas merepresentasikan operasi background seperti pembuatan laporan, kueri log, sinkronisasi perangkat, dan proses jangka panjang lainnya. |
| `update_api_ratelimit` | Perbarui konfigurasi rate limiting API. Mengonfigurasi rate limit untuk operasi baca dan tulis API. Fitur ini tersedia di FortiAnalyzer 7.6.5 dan seterusnya. |
| `wait_for_task` | Tunggu hingga tugas selesai. Mem-poll status tugas hingga selesai atau timeout. |

### Trafik (1)

| Tool | Deskripsi |
|------|-----------|
| `analyze_policy_traffic` | Uraikan trafik apa yang sebenarnya dibawa oleh masing-masing kebijakan firewall. Mengganti get_policy_traffic_profile, get_policy_port_analysis, dan get_policy_protocol_summary: ketiganya hanya berbeda pada breakdown yang dihasilkan, yang kini menjadi parameter sample_by. Ini adalah *sampel terbatas*, bukan sensus. Ia memindai jumlah slice waktu yang tetap per kebijakan dan berhenti di batas baris, jadi periksa `is_exact` sebelum mengutip angka apa pun. Ketika False, `analysis_mode` adalah "bounded_sample" dan `total_hits` adalah lantai, bukan total. Gunakan query_logs(sample_by=[...]) alih-alih ketika Anda ingin satu set agregat untuk satu kueri; tool ini menyebar hingga MAX_POLICY_IDS kebijakan di bawah anggaran kueri bersama dan melaporkan masing-masing secara terpisah. |

### UEBA (5)

| Tool | Deskripsi |
|------|-----------|
| `get_endpoint_stats` | Dapatkan statistik jumlah endpoint (aset) UEBA tingkat ADOM untuk suatu jendela. Mengembalikan snapshot jumlah agregat untuk ADOM di atas jendela: total jumlah endpoint, baru, teridentifikasi, dan tidak teridentifikasi. Ini adalah penyebut skala estate, BUKAN record per-endpoint atau time-series. FortiAnalyzer memerlukan jendela waktu, jadi selalu dikirim. Memerlukan UEBA diaktifkan/berlisensi di FortiAnalyzer. |
| `get_endpoint_vulnerabilities` | Dapatkan record CVE/kerentanan untuk endpoint UEBA. Mengembalikan daftar kerentanan per-endpoint (id CVE, severity, tipe, deskripsi, referensi) seperti yang dideteksi oleh FortiClient atau FortiGate. Memerlukan UEBA diaktifkan/berlisensi di FortiAnalyzer. |
| `get_endpoints` | Dapatkan record endpoint (aset) UEBA dari FortiAnalyzer. Menyelesaikan profil endpoint/aset: nama dan IP (``epname``/``epip``), perangkat pendeteksi, dan daftar asosiasi ``user``. Memerlukan UEBA diaktifkan/berlisensi di FortiAnalyzer. |
| `get_enduser_stats` | Dapatkan statistik jumlah end-user (identitas) UEBA tingkat ADOM untuk suatu jendela. Mengembalikan objek jumlah agregat untuk ADOM di atas jendela: total jumlah end-user dan yang baru. Ini adalah penyebut skala estate, BUKAN record per-user atau time-series. FortiAnalyzer memerlukan baik jendela maupun item statistik yang diminta, jadi keduanya selalu dikirim. Memerlukan UEBA diaktifkan/berlisensi di FortiAnalyzer. |
| `get_endusers` | Dapatkan record end-user (identitas) UEBA dari FortiAnalyzer. Menyelesaikan record identitas pengguna yang ber kunci ``euname``. Dengan detail_level "extended", juga mengembalikan ``email``. Memerlukan UEBA berlisensi di FAZ. |

## Pengembangan

```bash
pip install -e ".[dev]"
ruff check src
pytest
```