# ADR-005: Bounded Health Cooldown and Recovery

- **Status:** accepted untuk Fase 2
- **Scope:** passive feedback, active probe scheduling, picker eligibility, dan recovery state machine
- **Context:** counter kumulatif sebelumnya tidak menyediakan cooldown atau backoff yang dapat diprediksi. Node yang gagal dapat dipilih kembali terlalu cepat, dan pemulihan tidak memiliki hysteresis.
- **Decision:**
  - kegagalan koneksi pertama memberi cooldown 30 detik;
  - tiga kegagalan berturut-turut memindahkan node ke `dead` dan mengeluarkannya dari traffic nyata;
  - active probe untuk node `dead` memakai backoff 60, 120, 300, 900, lalu 3600 detik;
  - satu probe sukses memulihkan node ke `degraded`, tiga sukses berturut-turut memulihkannya ke `healthy`;
  - state `dead`/`quarantine` tetap tidak eligible untuk traffic sampai probe sukses; cooldown dan backoff hanya mengatur kapan probe boleh dijalankan;
  - CONNECT valid tanpa kandidat eligible menghasilkan 503 cepat; retry tetap hanya boleh terjadi sebelum respons CONNECT 200/byte client.
- **Consequences:** health state tersimpan bersama timestamp cooldown/probe dan counter berturut-turut. SQLite schema lama dimigrasikan saat dibuka. Recovery lebih lambat daripada retry langsung, tetapi mencegah flapping dan retry storm.
- **Evidence:** `tests/test_health_control.py`, `tests/test_picker_failover.py`, `tests/test_probe.py`, dan `tests/test_generation_gateway.py` memverifikasi cooldown, backoff/hysteresis, empty-pool 503, pre-forward failover, no-fallback forced node, serta relay streaming.
