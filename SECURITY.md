# Security and Privacy

## Data Sensitif

Hopline memperlakukan hal berikut sebagai secret:

- URL subscription;
- UUID, password, atau credential node;
- token Control API;
- secret Clash API;
- API key atau credential yang kebetulan lewat konfigurasi client.

Secret tidak boleh muncul di log, metrics, exception, error response, fixture publik, repository, atau output CLI.

## Aturan Penyimpanan

- File konfigurasi yang memuat secret wajib berpermission `0600`.
- Direktori data wajib hanya dapat dibaca oleh user service.
- Output diagnostik harus memask secret dan credential.
- URL subscription tidak boleh ditulis penuh pada log.
- Database dan backup yang menyimpan credential harus diperlakukan sebagai data sensitif.

## Traffic

Hopline tidak melakukan MITM. Gateway hanya melihat metadata koneksi minimum yang diperlukan untuk routing dan operasi, seperti node ID, host tujuan tanpa path/query, hasil, dan latensi.

Retry otomatis hanya diperbolehkan sebelum byte client diteruskan. Setelah forwarding dimulai, Hopline tidak boleh mengulang POST, SSE, atau stream lain.

## Input Tidak Tepercaya

Subscription adalah input eksternal. Parser wajib:

- membatasi ukuran body dan jumlah node;
- memvalidasi protokol, host, port, dan field transport;
- mengabaikan entri rusak tanpa crash seluruh sync;
- tidak menggunakan `eval`, import dinamis, atau eksekusi isi subscription;
- mempertahankan snapshot valid terakhir jika fetch gagal.

## Network Exposure

Default semua endpoint bind ke `127.0.0.1`:

- Gateway: `18770`;
- sing-box inbound: `18771`;
- Control API: `18772`;
- sing-box control API: `18773`.

Jika gateway dibuka ke interface luar, autentikasi wajib dan konfigurasi harus menghasilkan peringatan keras.

## Pelaporan Masalah

Jangan memasukkan credential atau URL subscription asli saat melaporkan masalah. Redact konfigurasi dan gunakan fixture sintetis. Laporan keamanan harus menjelaskan dampak, kondisi pemicu, dan langkah reproduksi yang aman.
