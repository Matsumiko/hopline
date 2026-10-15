# ADR-009: Controlled Exit-Country Metadata Refresh

- **Status:** accepted untuk country observability Fase 3
- **Scope:** pengisian metadata country berdasarkan exit IP node; bukan health probe dan bukan inferensi dari hostname
- **Evidence:** `hopline geo --node` berhasil memperoleh exit IP `2a07:14c0:1:520b::2` dengan country `RU`; registry production sebelumnya memiliki `1849` node dan `0` row geolocation

## Context

Status country hanya dapat menampilkan `ID`, `US`, `RU`, dan country lain jika metadata geolocation node sudah tersimpan. Metadata harus berasal dari exit IP aktual yang diperoleh melalui route node tersebut. Nama node, hostname relay, lokasi VPS, atau provider subscription tidak cukup untuk menentukan country exit.

## Decision

Hopline menyediakan refresh country eksplisit melalui:

```text
hopline geo --config <file> --node <node-id> --json
hopline geo --config <file> --all --concurrency 2 --json
```

Mode `--all`:

- memilih node tanpa metadata country fresh;
- melewati node `dead` dan `quarantine`;
- membatasi concurrency dengan semaphore;
- mengambil exit IP melalui Gateway memakai route `node-<id>`;
- menjalankan resolver geolocation fallback;
- menyimpan hanya IP, country, ASN, provider, dan timestamp;
- mengeluarkan ringkasan updated, failed, skipped, error class, dan country counts.

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

- Regression test memverifikasi node fresh/dead dilewati dan node missing diproses.
- Full suite setelah collector: `97 tests — OK`.
- Production smoke satu node menghasilkan country `RU` melalui exit IP aktual.
