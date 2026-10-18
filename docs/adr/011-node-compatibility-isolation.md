# ADR-011: Node Compatibility Isolation dan Normalisasi Fingerprint uTLS

- **Status:** accepted untuk lifecycle engine Fase 1
- **Scope:** penyaringan node yang tidak kompatibel dengan sing-box sebelum publish generation, plus normalisasi fingerprint uTLS. Bukan pengganti health dan bukan validasi field provider secara menyeluruh
- **Evidence:** production PC lokal crash-loop pada 2026-10-18 dengan `sing-box config rejected: unknown uTLS fingerprint: unsafe`; sing-box 1.14.3 menolak `unsafe` dan menerima `chrome`, `random`, `randomized`

## Context

Provider share link memakai flag fingerprint milik v2ray, termasuk nilai `unsafe` yang tidak dikenal sing-box. Parser meneruskan nilai tersebut apa adanya ke `tls.utls.fingerprint`. Karena satu config memuat seluruh outbound, satu node dengan fingerprint tidak valid membuat `sing-box check` gagal untuk seluruh generation. Engine tidak pernah publish generation, gateway tidak pernah bind, dan systemd masuk restart loop; control/metrics hanya hidup sesaat sebelum proses keluar.

Masalahnya berlapis: satu field provider yang tidak valid menjatuhkan seluruh pool, bukan hanya node tersebut.

## Decision

Normalisasi fingerprint di generator sebelum menulis config. Nilai yang termasuk set uTLS sing-box diteruskan; nilai yang tidak dikenal, termasuk `unsafe`, dipetakan ke profil default `chrome` ketika node memakai Reality dan dihilangkan (tanpa uTLS) ketika node tidak memerlukannya. Normalisasi berlaku untuk jalur share link maupun structured subscription karena berada di generator.

Sebelum publish generation, engine menyaring node yang config-nya tidak diterima sing-box. Pemeriksaan dilakukan pada seluruh set; jika gagal, engine melakukan bisection untuk mengisolasi node bermasalah dan membangun config dari node yang tersisa. Jika tidak ada node tersisa, engine gagal dengan error eksplisit.

Node yang ditolak tidak dimasukkan ke credential dan picker gateway, sehingga tidak menerima traffic dan tidak ditampilkan sebagai kandidat. `rotate`, `node-<id>`, sticky, country, dan capability route tetap mempertahankan perilaku untuk node yang diterima.

## Consequences

- Satu node provider yang tidak valid tidak lagi menumbangkan seluruh engine; generation dibangun dari node yang valid.
- Node yang ditolak tidak dapat dipilih sampai parameter providernya diperbaiki dan tersinkron ulang.
- Jalur normal menambah satu `sing-box check` per publish generation; jalur gagal memakai bisection dengan biaya subprocess `O(k log n)` untuk `k` node bermasalah.
- Fingerprint provider non-standar mengikuti profil default; ini mengubah perilaku handshake dibanding meneruskan nilai mentah, tetapi nilai mentah memang tidak dapat dijalankan.
- Belum ada metric atau log eksplisit untuk node yang ditolak; ini blind spot operasional yang perlu ditindaklanjuti.
- Validasi ini menargetkan kompatibilitas config sing-box, bukan kelengkapan seluruh field provider.

## Alternatives rejected

- Membiarkan perilaku lama: satu node invalid berarti total outage.
- Menolak node di registry saat parse: menyentuh lifecycle subscription dan membuang node secara permanen untuk masalah yang bersifat engine-side.
- Menjalankan `sing-box check` per node untuk semua node: biaya `N` subprocess pada setiap publish, tidak sepadan karena jalur normal sudah divalidasi sekali pada seluruh set.
- Meneruskan fingerprint mentah ke sing-box: sudah terbukti menolak config dan memicu restart loop.

## Confirmation

- Unit test normalisasi fingerprint: `unsafe` hilang pada node non-Reality dan menjadi `chrome` pada Reality; fingerprint valid dipertahankan.
- Unit test isolasi engine: satu node `ss` dengan method tidak dikenal tidak menghalangi generation; node ditolak tidak muncul di config; set yang seluruhnya invalid gagal eksplisit.
- Full discovery suite `109 tests — OK`.
- Deploy production PC lokal: service tetap `active`, tidak ada error journal setelah restart, gateway `18770` mengembalikan HTTP `200` untuk credential valid dan `407` untuk credential salah atau kosong.
