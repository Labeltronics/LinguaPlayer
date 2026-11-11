# Hasil verifikasi — 11 November 2026

Dijalankan di Linux, Python 3.11.

- 9 unit test core: PASS. Validasi timestamp, overlap, offset, Unicode, SRT roundtrip, export asli, silence, pembatalan, respons Gemini tidak lengkap, serta alur Gemini→Google Translate dengan API mock.
- Compile Python app.py/core.py: PASS.
- Qt offscreen UI smoke: PASS. Membuat jendela, mengisi tabel, mengedit terjemahan, dan menutup; mesin VLC di-mock.
- Integrasi worker dan FFmpeg: PASS. Menghasilkan video MP4 sintetis berdurasi 1 detik, mengekstrak WAV menggunakan executable imageio-ffmpeg, dan menerima sinyal hasil subtitle; API di-mock.

Belum diverifikasi: build EXE Windows, playback VLC riil, codec/video nyata lintas format, panggilan Gemini/Google Translate riil, kualitas ejaan/terjemahan, performa video panjang, pembatalan HTTP riil. Tidak ada API key pengguna tersedia. Tidak mengklaim EXE sudah dibuat atau semua modul sudah teruji end-to-end.

## Verifikasi tambahan

- Build Windows GitHub Actions #1: PASS. EXE startup, Qt, VLC 3.0.24, FFmpeg.
- Build Windows #2: PASS, termasuk roundtrip Windows Credential Manager (key sementara dummy dihapus setelah tes).
- Gemini API langsung dengan key pengguna: model lama 2.5 Flash menolak pengguna baru (404). Model gemini-3.8-flash berhasil menghasilkan 3 cue subtitle beserta terjemahan Indonesia pada sampel ucapan sekitar 12 detik. Key tidak ditulis ke source, GitHub atau log hasil.
- Qt offscreen buffered playback test (VLC mock): PASS. Default id, tampilan deteksi sumber, mulai setelah buffer siap, pause ketika coverage habis, dan pause manual dipertahankan.
- Mode bertahap memproses 10 detik per permintaan, bukan streaming suara live. Jeda buffer tetap mungkin bila API lambat.

- 11 tes otomatis (9 core + 2 player) lulus pada Linux, termasuk worker FFmpeg 12 detik dengan dua chunk (API mock).
- Prompt terjemahan diatur untuk bahasa alami sesuai konteks; target id meminta ejaan Indonesia baku. Ini petunjuk model, bukan jaminan mutu profesional.

## Pembaruan playlist, pemutar ganda, 3D dan timeout

32 tes otomatis lulus di Linux: termasuk timeout socket, Retry-After, penolakan akses tanpa retry, penghentian kuota harian, penyamaran key, resume setelah chunk gagal, dua controller independen, shortcut seek, speed, playlist Unicode/relative paths, komposisi anaglyph, pertukaran mata, clipping pergeseran dan buffer RV32 sejajar 32 byte. Tampilan diperiksa pada lebar 960 piksel agar dua jendela dapat berdampingan.

Tes EXE Windows diperluas untuk memutar delapan format nyata dengan VLC sistem dinonaktifkan, seek 60 detik, speed 1.5×, dua video bersamaan, frame anaglyph melalui callback VLC, PiP saat 3D, kembali ke output native, fullscreen, dan auto-next playlist. Hasil akhir tersedia pada log GitHub Actions build pembaruan ini. Tes ini tidak memanggil Gemini langsung; masalah timeout pada jaringan pengguna atau penolakan proyek masih perlu diverifikasi setelah pengguna menjalankan versi baru.
