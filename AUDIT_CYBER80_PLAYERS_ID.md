Lihat **CYBER80_BROWSER_3D_ID.md** dan **GEMINI_LIVE_TEST_REPORT.json** untuk pembaruan terbaru. Bagian berikut adalah catatan audit versi sebelumnya.

# Status audit terbaru

Lihat **PEMBARUAN_CYBER80_ID.md** untuk fitur baru, hasil uji dan kekurangan yang masih terbuka. Tabel di bawah adalah audit versi sebelumnya; beberapa batasan (skin, track AI, SQLite, kompresor, attachment) sudah berubah pada pembaruan ini.

# Audit dan roadmap Cyber80 Players

Tanggal audit: 11 November 2026. Dasar pemeriksaan: kode aplikasi, tes otomatis, dan build Windows x64. Ini daftar temuan yang diketahui, bukan jaminan bahwa seluruh cacat perangkat lunak sudah ditemukan. Sasaran produk adalah pemutar video/audio dengan subtitle AI, dua jendela independen, profil suara, 3D anaglyph, dan alat peningkatan resolusi.

## Penilaian profesional

Versi awal sudah berfungsi sebagai prototipe pemutar berbasis VLC, tetapi belum cukup untuk disebut pemutar universal atau aplikasi yang sempurna. Kekuatan utamanya adalah runtime VLC/FFmpeg yang dibundel, penyimpanan key melalui Windows Credential Manager, pemutaran dua video, PiP, dan subtitle Gemini. Kelemahan utamanya berada pada ketergantungan API, pemulihan sesi, cakupan pengujian codec, kontrol audio, batas GPU/HDR, dan distribusi aplikasi.

Versi Cyber80 menambahkan perbaikan nyata pada area tersebut. Fitur yang bergantung pada layanan/model lokal atau perangkat GPU tetap membutuhkan prasyarat yang dijelaskan di bawah.

## Temuan, dampak dan status

| Area | Kekurangan sebelumnya / risiko | Perbaikan pada Cyber80 | Batasan yang masih berlaku |
|---|---|---|---|
| Klaim codec | Ekstensi bukan codec; satu MKV dapat berisi codec berbeda. | Seluruh plugin VLC resmi dibundel, daftar DLL tersedia, filter file mencakup video dan audio. | Tidak dapat menjamin codec proprietari, DRM, file korup, atau semua varian container. |
| Format audio | Dialog dan penambahan folder hanya memprioritaskan video. | Audio MP3, WAV, AAC, FLAC, Ogg, Opus, M4A/ALAC, WMA, AIFF dan lainnya dapat masuk playlist. | Dukungan aktual tetap mengikuti decoder VLC. MIDI/soundfont khusus tidak dijanjikan. |
| Equalizer | Tidak ada penyesuaian frekuensi atau preset. | EQ native 10 band, preamp, 13 preset aplikasi, preset pribadi, impor/ekspor dan bypass. | Ini bukan DAW, Dolby Atmos, atau pemisahan vokal berbasis AI. |
| Preset malam | Pengurangan ledakan/dialog belum tersedia. | Preset Malam/Lembut dan Dialog mengubah kurva EQ; auto-headroom mengurangi boost. | Bukan kompresor dinamis, limiter, atau normalisasi loudness. |
| Kontrol suara | Track dan sinkron audio belum tersedia di UI. | Pemilihan track, Stereo/Balik stereo/Kiri/Kanan, offset audio ±5 detik. | Track AI masih memakai track audio default, bukan selalu track yang dipilih untuk pemutaran. |
| Fullscreen | Tombol dapat kurang terlihat di toolbar. | Tombol langsung dekat Play/PiP, tombol PiP, F11 dan Esc. | Resolusi fisik mengikuti layar dan OS. |
| PiP | Perpindahan native window berpotensi kehilangan posisi pada klik cepat. | Rebinding dengan generasi permintaan; perintah lama tidak menghidupkan video kembali setelah Stop. | Kompatibilitas window/driver tetap perlu diuji pada perangkat pengguna. |
| Posisi menonton | Tidak pulih setelah aplikasi ditutup. | Posisi tersimpan berkala, dikenali berdasarkan identitas/ukuran/mtime file. | File yang dipindah/diubah dianggap identitas berbeda. |
| Bookmark dan pengulangan | Tidak ada alat adegan. | Bookmark tersimpan, A–B repeat, screenshot, thumbnail saat seek. | Belum merupakan editor video nonlinier atau pemotong klip. |
| Perpustakaan media | Daftar hanya berupa lokasi file. | Pencarian daftar, riwayat lokal, poster JPG/PNG lokal, tambah folder, repeat/shuffle. | Belum ada katalog online, pengenalan judul otomatis, atau sinkronisasi lintas perangkat. |
| Profil per film | Setelan perlu diulang. | Profil renderer, 3D, audio EQ/channel/delay, subtitle, warna dan kecepatan per media. | Volume/mute tetap milik masing-masing jendela agar tidak mengejutkan saat dua film dibuka. |
| Timeout Gemini | Socket timeout dapat langsung menggagalkan pekerjaan. | Timeout ditangkap; retry terbatas, Retry-After, detail error yang menyamarkan key. | Server/jaringan tetap bisa timeout; pembatalan permintaan aktif menunggu batas waktu. |
| Kuota gratis | Banyak panggilan dapat ditolak. | Permintaan antarjendela diserialkan dan diberi jeda; tidak ada fallback otomatis berbayar. | Aplikasi tidak bisa memastikan billing hanya dari key. Free Tier/kuota ditentukan Google. |
| Cache subtitle | Hasil hilang saat aplikasi ditutup. | Checkpoint atomik di disk, hasil lengkap dipakai ulang tanpa API, pemulihan bagian yang gagal. | Cache menyimpan teks lokal tanpa enkripsi; key API tidak ikut disimpan. |
| Batas potongan audio | Potongan 10 detik dapat memisahkan kata/konteks. | Tumpang tindih satu detik dan instruksi batas konteks mengurangi pengulangan. | Belum memakai forced alignment atau konteks cerita satu film penuh. |
| Akurasi terjemahan | Nama, aksen, istilah dan suara bising bisa salah. | Kamus istilah, prompt penerjemah profesional, editor dan pencarian subtitle. | Tidak ada sistem yang menjamin terjemahan/timestamp 100%. |
| AI lokal | Tidak ada alternatif tanpa API. | Adapter Whisper.cpp untuk STT dan Ollama untuk terjemahan melalui loopback. Proxy dan redirect dinonaktifkan. | Server dan model harus dipasang terpisah; bobot model tidak dibundel. Kualitas tergantung model. |
| GPU Cinema | GDI mengutamakan kompatibilitas, bukan kinerja maksimum. | Pilihan D3D11 GPU dan pengaturan warna/ketajaman tersedia. | Driver, codec, GPU dan efek CPU dapat membatasi akselerasi. Pilihan mode bukan bukti GPU benar-benar aktif. |
| 3D | Video 2D tidak mempunyai informasi kedalaman objek. | Anaglyph merah–cyan/biru, SBS/TB, tukar mata, geser tiap mata. | Pada sumber 2D hanya pergeseran bidang. Render anaglyph masih CPU, maksimal 960×540. |
| HDR | Tidak ada kalibrasi/tone mapping khusus aplikasi. | Jalur native VLC/OS dapat digunakan lewat mode D3D11. | HDR, Dolby Vision, gamut, dan akurasi warna belum diverifikasi pada monitor HDR fisik. |
| HD/FHD/4K | Tidak ada ekspor peningkatan resolusi. | Ekspor 720p/1080p/2160p, Lanczos dan ketajaman CPU; pilihan encoder GPU. | Upscale biasa tidak memulihkan detail hilang. Ekspor tidak membakar subtitle/3D UI. |
| Encoder GPU | Belum ada diagnosis kemampuan build. | Daftar encoder/filter FFmpeg dibaca; ketidaktersediaan menghasilkan error jelas. | Encoder yang dikompilasi belum membuktikan driver/perangkat cocok. GPU fisik tidak diuji di CI. |
| Ekspor | Risiko menimpa sumber/hasil setengah jadi. | Sumber tidak boleh sama dengan tujuan; hasil sementara diganti atomik setelah berhasil; pembatalan tersedia. | Ruang disk, temperatur, daya, dan waktu ekspor bergantung perangkat. |
| Pengujian | Sampel pendek tidak mewakili semua film. | Tes unit, pemutaran beberapa codec video/audio, EQ, dua pemain, PiP, scene tools, dan ekspor. | Belum ada laboratorium hardware, uji 24 jam, fuzzy media corpus, atau jaminan bebas crash. |
| Distribusi | Paket portable belum bertanda tangan penerbit. | Runtime dibundel, panduan dan laporan audit tersedia. | Code signing, installer, update otomatis dan rollback belum disediakan. |

## Arsitektur dan batas sumber daya

Setiap jendela mempunyai pemutar VLC, playlist dan kontrol sendiri. Permintaan Gemini diserialkan dalam satu proses. Riwayat/profil lokal dibagi oleh jendela dalam proses yang sama; koordinasi beberapa proses aplikasi atau beberapa komputer belum disediakan. Cache subtitle menggunakan identitas file, model, target bahasa, kamus dan mesin AI; mengganti konfigurasi menghasilkan cache baru.

Audio dikirim ke Google hanya saat mesin Gemini dipilih dan pengguna memulai proses. Mode AI lokal hanya menerima URL HTTP localhost, 127.0.0.1 atau ::1, tanpa redirect/proxy. Windows Credential Manager menyimpan key; cache subtitle/profil tidak menyimpan key. File sumber tidak diubah oleh 3D, EQ atau pengaturan tampilan.

Ekspor NVIDIA memakai skala CUDA dan encoder NVENC, dengan padding melalui memori CPU. Intel memakai QSV/VPP dan encoder QSV, juga dapat memerlukan transfer/padding CPU. AMD AMF memakai encoder GPU dengan skala CPU. Ini bukan klaim bahwa semua tahap bekerja di GPU atau bahwa semua GPU didukung.

## Ide lanjutan yang belum diimplementasikan

1. **Dialogue AI dan smart loudness:** pemisahan dialog/bising, pengukuran LUFS, limiter dan kompresor adaptif. Memerlukan DSP/model dan pengukuran audio, bukan sekadar preset EQ.
2. **Cinema-grade super-resolution:** model AI GPU dengan motion consistency, bukan hanya memperbesar frame. Harus diuji terhadap artefak, lisensi model, VRAM, temperatur dan latensi.
3. **True 2D-to-3D depth:** estimasi depth dan rendering mata kedua dengan penanganan area tertutup. Tidak boleh dipromosikan sebagai kedalaman asli dari sumber 2D.
4. **AI scene search semantik:** mencari adegan berdasarkan makna dan ringkasan lokal, dengan indeks yang dapat dihapus pengguna.
5. **Media library lanjutan:** database SQLite, thumbnail massal, deteksi file berpindah, metadata poster daring opsional dan subtitle manager.
6. **Review subtitle profesional:** forced alignment, speaker diarization, versi terjemahan, glossary per proyek dan pengukuran WER/BLEU/penilaian manusia.
7. **HDR/GPU lab:** matriks NVIDIA/Intel/AMD, H.264/H.265/AV1/10-bit, layar SDR/HDR, tone mapping dan output audio HDMI/passthrough.
8. **Distribusi produksi:** installer, code signing, pembaruan bertanda tangan, rollback, crash dump opt-in, serta pengujian aksesibilitas dan keyboard lengkap.

## Cara membaca hasil uji

`HASIL_UJI_WINDOWS.json` dalam paket mencatat hasil otomatis dari EXE Windows. Hasil PASS berlaku pada sampel dan skenario yang diuji, bukan semua file pengguna. Uji audio memeriksa decoding dan penerapan parameter EQ, bukan kualitas akustik speaker/headphone. Adapter AI lokal diuji melalui server loopback tiruan; model lokal sungguhan dan inference Gemini tambahan tidak dipakai untuk menghabiskan kuota pengguna.

Prioritas selanjutnya: validasi pada file nyata pengguna, perbaikan berdasarkan log yang dapat direproduksi, lalu pengujian perangkat GPU/HDR dan kualitas subtitle. Produk yang matang diperoleh dari pengujian berulang dan pemeliharaan, bukan klaim “sempurna”.
