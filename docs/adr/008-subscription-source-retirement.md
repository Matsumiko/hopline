# ADR-008: Retire Removed Subscription Sources After Complete Sync

- **Status:** accepted untuk lifecycle subscription Fase 1
- **Scope:** ownership source subscription, node-source reconciliation, dan scheduler batch boundary
- **Evidence:** `hopline/registry.py`, `hopline/scheduler.py`, `tests/test_structured_hysteresis.py`, `tests/test_scheduler_cli.py`

## Context

Konfigurasi subscription dapat berubah: URL lama dihapus atau diganti, sementara node yang sama dapat dimiliki beberapa source. Menghapus source lama tanpa memperhatikan ownership dapat membuang node yang masih dipakai source lain. Sebaliknya, tidak pernah merekonsiliasi source lama meninggalkan snapshot dan node stale di registry.

Sync juga dapat berhenti saat shutdown sebelum semua source diproses. Retirement pada siklus parsial dapat menghapus source yang belum sempat dicoba.

## Decision

`SubscriptionScheduler` hanya memanggil `SQLiteRegistry.reconcile_subscription_sources()` setelah seluruh subscription dan static-node entries dalam satu siklus selesai tanpa stop request. Registry:

- menghapus snapshot subscription yang tidak ada dalam daftar source aktif;
- membiarkan source `static:<node-id>` tetap dikelola oleh static-node sync;
- mengandalkan foreign keys untuk menghapus hubungan `node_sources`, removal counters, dan metadata turunan source;
- menghapus node yang tidak lagi memiliki hubungan source apa pun;
- mempertahankan node yang masih dimiliki source aktif lain.

Hysteresis tiga valid snapshot tetap berlaku untuk node yang hilang dari source yang masih aktif. Fetch atau parse failure memakai snapshot valid terakhir dan tidak memicu retirement.

## Consequences

- Mengganti atau menghapus URL subscription mulai berlaku setelah satu siklus sync lengkap.
- Node shared tidak terhapus ketika satu source di-retire.
- Shutdown aman terhadap retirement yang tidak lengkap, tetapi source lama baru dibersihkan pada siklus lengkap berikutnya.
- Retirement menghapus data source yang tidak lagi dideklarasikan; konfigurasi aktif menjadi authority untuk source subscription.

## Alternatives rejected

- **Retire segera saat konfigurasi dibaca:** dapat menghapus node sebelum source baru berhasil disinkronkan.
- **Tidak pernah retire otomatis:** meninggalkan snapshot dan node stale setelah URL diganti.
- **Retire setelah setiap source selesai:** siklus multi-source dapat sementara menghapus node shared/source yang belum diproses.

## Confirmation

- `test_retiring_source_removes_orphans_but_keeps_shared_nodes` membuktikan source lama dan orphan node dihapus, sedangkan shared node dan source aktif dipertahankan.
- `test_scheduler_does_not_retire_sources_after_partial_cycle` membuktikan stop di tengah siklus tidak menjalankan retirement.
- Full suite terakhir: 92 test lulus dengan `ResourceWarning` diperlakukan sebagai error.
- Runtime production refresh belum dikonfirmasi karena akses SSH VPS ditolak; service lokal hanya diperiksa read-only.
