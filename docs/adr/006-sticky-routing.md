# ADR-006: Process-Local Sticky Routing

- **Status:** accepted untuk Fase 3 slice routing
- **Scope:** username `sticky-<sessionId>`, session binding, TTL, dan rebind sebelum CONNECT 200
- **Decision:** sticky bindings disimpan in-memory di proses Gateway dengan default idle TTL 10 menit. Binding dibuat atau diperpanjang hanya setelah upstream mengembalikan HTTP 200. Koneksi baru dengan session yang sama mencoba node binding terlebih dahulu. Jika binding expired, dead, cooldown, atau gagal sebelum 200, Gateway memilih kandidat sehat lain dan mem-bind ulang session tersebut. Setelah byte client diteruskan, tidak ada retry atau rebind.
- **Compatibility:** `rotate` tetap memilih kandidat per koneksi; `node-<id>` tetap forced tanpa fallback; credential lokal tetap dipisahkan dari credential node.
- **Consequences:** restart proses menghapus sticky bindings dan sesi akan memilih ulang. Sticky state tidak ditulis ke SQLite karena merupakan affinity sementara, bukan data node atau subscription. TTL dapat diuji dengan injected clock/store.
- **Evidence:** `tests/test_sticky.py` dan `tests/test_gateway_sticky.py` mencakup TTL, same-session reuse, rebind saat node dead, serta relay lifecycle.
