# Cyber80 Players — pembaruan modern & subtitle attachment

Tanggal: 11 November 2026. Kode dan pengujian diperbarui; hasil EXE Windows ada di HASIL_UJI_WINDOWS.json. Tidak ada API key ditanamkan ke EXE atau repositori.

## Fitur baru yang tersedia

- Personalisasi: Cyber Neon, Cinema Black, Light, AMOLED, High Contrast; aksen warna; impor/ekspor skin JSON yang hanya menerima lima warna #RRGGBB. Skin tidak menjalankan skrip atau memuat URL. Layout dock dapat disimpan/dipulihkan. Mode sederhana menyembunyikan kontrol lanjutan; panel pengaturan dapat digulir untuk layar pendek.
- Subtitle overlay: label transparan di atas area video, warna/ukuran dan jarak dari bawah, bayangan gelap, tanpa menangkap klik. Tersedia opsi kembali ke panel subtitle. Overlay tampak ketika jendela video aktif, mengikuti area video/PiP; kompatibilitas compositor Windows/HDR harus diuji pada perangkat pengguna. Native ASS/SSA/VTT/SRT juga dapat dimuat melalui VLC.
- Pemutaran: chapter, lompat ke detik, frame berikutnya (belum frame mundur), aspect ratio, crop, deinterlace, rotasi/cermin. Fullscreen menyembunyikan tombol setelah mouse diam tiga detik; gerakkan mouse untuk memunculkannya.
- Subtitle editor: VTT, sinkronisasi affine dua titik, pemeriksaan panjang baris, jumlah baris, karakter/detik, dan tumpang tindih. Ini bukan forced alignment atau bukti akurasi terjemahan.
- Subtitle audio: ukuran potongan 10–60 detik (default UI 30), pilihan siapkan dahulu / tunggu subtitle / lanjut tanpa menunggu. Potongan lebih besar mengurangi frekuensi permintaan, tetapi tidak menjamin latensi real-time. Track audio sumber AI menggunakan nomor urut FFmpeg 0,1,... yang dipilih eksplisit, bukan ID track VLC. Gunakan Info track AI.
- Koleksi SQLite: migrasi riwayat JSON lama satu kali; transaksi untuk perubahan lintas proses; favorit, watched/unwatched, daftar koleksi, dan relink file manual. Relink membawa riwayat/profil/bookmark, bukan cache subtitle. Belum ada poster daring, deteksi judul serial, atau relink otomatis berbasis hash.
- Audio: pemilihan perangkat output yang dilaporkan VLC, DSP native normalisasi volume atau kompresor malam. Efek diterapkan dengan memulai ulang engine sambil memulihkan posisi. Ini bukan pemisahan dialog AI, limiter true-peak terukur, kalibrasi LUFS, atau jaminan kualitas akustik.
- Dual player: sinkronisasi play/pause, kecepatan, waktu dan offset dengan satu pengendali; toleransi koreksi sekitar 400 ms. Bukan sinkronisasi frame akurat, tidak aktif selama AI audio berjalan, dan tampilan tetap dua jendela.
- Alat media offline: potong klip MP4 dengan re-encode, ekstrak WAV/MP3, normalisasi audio WAV satu pass loudnorm (-16 LUFS target), remux MKV, bakar subtitle editor ke MP4. Tidak menimpa sumber, menulis output sementara unik dan commit atomik, dapat dibatalkan. Normalisasi satu pass tidak menjamin seluruh file tepat -16 LUFS; remux bergantung kompatibilitas stream. Clip bukan stream-copy/lossless.
- Privasi: sesi tanpa penulisan riwayat/cache baru, ukuran cache, hapus semua cache dengan konfirmasi, ekspor diagnosis tanpa API key dan path media. Mode privat tidak menghapus riwayat lama atau menonaktifkan log VLC/jejak OS; file SRT/ekspor yang diminta tetap disimpan.

## Buat subtitle dahulu menggunakan attachment video

1. Buka **Subtitle latar belakang → Buat dari attachment video** atau tombol pada panel Subtitle / AI.
2. Isi key Gemini sendiri; bahasa tujuan default Indonesia. Key dapat disimpan di Windows Credential Manager.
3. Pilih video yang akan dikirim ke Google dan lokasi hasil `.srt`. Pemilihan lokasi ini dilakukan sebelum pekerjaan dimulai.
4. Jika format/ukuran tidak diterima, aktifkan **Proxy MP4 720p**. Proxy juga diperlukan untuk memilih track audio selain yang pertama. Sumber tidak diubah; proxy H.264/AAC bersifat sementara. Pembuatan proxy menggunakan CPU dan memerlukan ruang disk.
5. Aplikasi mengunggah attachment sekali menggunakan Files API, menunggu status ACTIVE, lalu meminta transkripsi/terjemahan dalam interval 120 detik menggunakan referensi file yang sama. Ini mencegah satu respons harus memuat seluruh subtitle film panjang. Jeda permintaan dan penanganan quota Gemini tetap berlaku.
6. SRT disimpan otomatis setelah semua interval selesai. Muncul notifikasi tray Windows bila tersedia, atau dialog aplikasi bila tray tidak tersedia. Jika film tersebut masih dibuka dan tidak ada AI audio aktif, subtitle dimuat ke editor. Film lain tidak diubah.
7. Anda boleh menonton film lain atau meminimalkan aplikasi. **Aplikasi harus tetap berjalan; pekerjaan tidak berjalan sebagai Windows Service dan belum dilanjutkan setelah komputer mati secara otomatis.** Menutup saat attachment aktif ditolak sampai pekerjaan selesai/dibatalkan.
8. Jika gagal, file `.progress.json` dan `.partial.srt` disimpan di samping tujuan (kecuali sesi privat). Mulai lagi dengan sumber, konfigurasi dan tujuan sama untuk melanjutkan interval yang belum selesai; video tetap perlu diunggah ulang. File SRT final yang sudah ada tidak diganti sampai semua interval baru selesai.
9. Aplikasi mencoba menghapus attachment di Google setelah selesai/gagal. Jika penghapusan gagal, status menjelaskan bahwa pembersihan belum terkonfirmasi. Dokumentasi Google menyebut masa simpan Files API 48 jam.

Attachment langsung dibatasi aplikasi maksimum 2.000.000.000 byte untuk menjaga batas Free Tier konservatif. Batas konteks, token, jumlah permintaan, dan akses model masih berlaku. Video tidak otomatis murah hanya karena satu kali upload; inference tetap menggunakan kuota akun. Aplikasi tidak dapat memastikan billing dari API key. Tidak ada fallback berbayar otomatis.

Rujukan protokol resmi:
- https://ai.google.dev/gemini-api/docs/files
- https://ai.google.dev/gemini-api/docs/generate-content/video-understanding

## Pengujian dan batas bukti

63 tes otomatis mencakup seluruh fitur sebelumnya, skin tervalidasi, migrasi/transaksi SQLite dan relink, kebijakan buffering, VTT dan sinkronisasi, opsi DSP/rotasi, overlay input, protokol upload per blok, penolakan URL asing, redaksi key pada HTTP403, status FAILED/cancel, validasi timestamp, output terpotong, checkpoint/resume dan notifikasi tanpa mengganti subtitle film lain. Enam alat media dijalankan dengan FFmpeg sungguhan pada sampel; proxy TS→MP4 diuji sungguhan dengan respons Gemini tiruan.

Pengujian tidak mengirim film pengguna atau melakukan inference menggunakan key pengguna. Integrasi Gemini attachment diuji melalui mock protokol, belum bukti penerimaan model/akun atau akurasi film nyata. Laporan Windows mencatat tes pemutaran EXE dengan VLC sistem dinonaktifkan, codec sampel, PiP, dua pemain, EQ, CPU upscale dan kontrol baru. Tidak menjamin semua codec atau bebas bug.

## Saran audit yang BELUM selesai

- AI super-resolution temporal, depth 2D→3D, shader GPU anaglyph, pemisahan dialog AI dan pencarian adegan semantik.
- Streaming URL/reconnect/NAS terpadu, casting, remote ponsel ber-pairing.
- Poster grid/metadata daring, serial-musim-episode, scan folder otomatis, thumbnail massal.
- Frame mundur presisi, pan/zoom interaktif, subtitle forced alignment/diarization, penilaian terjemahan manusia.
- Crossfade/ReplayGain/passthrough tervalidasi, limiter true peak, profil DSP/perangkat/rotasi persisten per film.
- Installer bertanda tangan, updater terverifikasi/rollback, crash reporter opt-in, audit screen reader dan uji DPI/hardware/HDR/24 jam.
- Antrean banyak film attachment, proses service setelah aplikasi ditutup, pembatalan HTTP aktif seketika, resume upload lintas restart, dan retry upload berbasis query offset.

Modul-modul tersebut tidak disamarkan sebagai fitur selesai. Membutuhkan implementasi, model/perangkat tambahan dan pengujian terpisah. Versi ini adalah peningkatan fungsional yang dapat diuji, bukan klaim semua saran sudah selesai atau sempurna.
