# ADR-009: Controlled Exit-Country Metadata Refresh

- **Status:** accepted untuk country observability Fase 3
- **Scope:** pengisian metadata country berdasarkan exit IP node; bukan health probe dan bukan inferensi dari hostname
- **Evidence:** `hopline geo --node` berhasil memperoleh exit IP `2a07:14c0:1:520b::2` dengan country `RU`; registry production sebelumnya memiliki `1849` node dan `0` row geolocation

## Context

Status country hanya dapat menampilkan `ID`, `US`, `RU`, dan country lain jika metadata geolocation node sudah tersimpan. Metadata harus berasal dari exit IP aktual yang diperoleh melalui route node tersebut. Nama node, hostname relay, lokasi VPS, atau provider subscription tidak cukup untuk menentukan country exit.

Hopline menyediakan refresh country eksplisit dan otomatis melalui batch collector. Manual:

```text
hopline geo --config <file> --node <node-id> --json
hopline geo --config <file> --all --concurrency 2 --json
```

Daemon juga menjalankan collector background setelah Gateway aktif, dengan default interval 900 detik, limit 10 node per siklus, dan concurrency 1. Cache `country_max_age` mencegah lookup metadata fresh.

Mode batch memilih node tanpa metadata country fresh, melewati node `dead` dan `quarantine`, mengambil exit IP melalui Gateway memakai route `node-<id>`, menjalankan resolver geolocation fallback, dan menyimpan hanya metadata non-secret.

Refresh tidak dijalankan pada setiap request `/status`, karena 1.849 node berarti ribuan koneksi proxy dan lookup provider. `/status` hanya membaca cache metadata yang sudah tersimpan.

## Consequences

- `/status` dapat menampilkan country nyata setelah refresh berhasil, misalnya `RU`, `ID`, atau `US`.
- Country belum diketahui tetap muncul sebagai `unknown`.
- Provider geolocation dan node dapat gagal atau rate-limit; hasil gagal tidak mengisi country palsu.
- Refresh batch adalah operasi eksplisit dan dapat dijalankan ulang; metadata fresh dilewati sampai melewati `country_max_age`.
- Health dan country tetap merupakan state terpisah.

## Alternatives rejected

- Menebak country dari hostname atau nama node: tidak membuktikan lokasi exit.
- Menjalankan lookup otomatis pada setiap `/status`: lambat, membebani node, dan melanggar batas provider.
- Menggunakan lokasi server health probe: lokasi target probe bukan lokasi exit node.

## Confirmation
- Regression test memverifikasi node fresh/dead dilewati, node missing diproses, dan background task dibatalkan bersih saat shutdown.
- Full suite setelah auto-refresh: `98 tests — OK`.
- Production smoke sebelumnya menghasilkan country `RU`, `JP`, dan `US` melalui exit IP aktual.
