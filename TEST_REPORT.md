# Hasil verifikasi — 11 November 2026

Dijalankan di Linux, Python 3.11.

- 9 unit test core: PASS. Validasi timestamp, overlap, offset, Unicode, SRT roundtrip, export asli, silence, pembatalan, respons Gemini tidak lengkap, serta alur Gemini→Google Translate dengan API mock.
- Compile Python app.py/core.py: PASS.
- Qt offscreen UI smoke: PASS. Membuat jendela, mengisi tabel, mengedit terjemahan, dan menutup; mesin VLC di-mock.
- Integrasi worker dan FFmpeg: PASS. Menghasilkan video MP4 sintetis berdurasi 1 detik, mengekstrak WAV menggunakan executable imageio-ffmpeg, dan menerima sinyal hasil subtitle; API di-mock.

Belum diverifikasi: build EXE Windows, playback VLC riil, codec/video nyata lintas format, panggilan Gemini/Google Translate riil, kualitas ejaan/terjemahan, performa video panjang, pembatalan HTTP riil. Tidak ada API key pengguna tersedia. Tidak mengklaim EXE sudah dibuat atau semua modul sudah teruji end-to-end.
