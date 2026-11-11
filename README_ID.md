# Cyber80 Players

Pemutar video/audio Windows x64 berbasis libVLC, dengan dua jendela independen, playlist, PiP/fullscreen, 3D anaglyph, Audio Studio, Scene Tools, profil per media, subtitle Gemini dan adapter AI lokal. Sebelumnya bernama LinguaPlayer; repository tetap memakai nama lama agar riwayat tidak terputus.

Jalankan **Cyber80Players.exe** dari paket hasil build setelah mengekstrak seluruh ZIP. Panduan lengkap ada pada **QUICK_START_ID.txt**. Audit temuan dan roadmap ada pada **AUDIT_CYBER80_PLAYERS_ID.md**. Konfigurasi layanan/model lokal dijelaskan pada **AI_LOKAL_ID.md**. Hasil penerimaan EXE tercatat di **HASIL_UJI_WINDOWS.json** dalam paket hasil build.

## Build sumber pada Windows

Pasang Python 3.12 x64 dan VLC x64 resmi, lalu jalankan `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. Hasilnya berada pada `dist\Cyber80Players\Cyber80Players.exe`. Bagikan seluruh folder. Skrip membuat ikon, menjalankan tes, membundel VLC/FFmpeg dan seluruh plugin VLC, serta membuat daftar CODEC_PLUGINS.txt.

Workflow GitHub Actions membangun pada Windows, menonaktifkan VLC sistem setelah bundling, lalu memeriksa pemutaran dengan runtime bawaan. Pengujian menggunakan video/audio sintetis, tidak mengirim key atau audio pengguna ke Gemini. Test adapter AI lokal memakai server HTTP loopback tiruan, bukan model sesungguhnya.

## Perhatian penggunaan

Gunakan proyek Gemini Free Tier tanpa billing. Aplikasi tidak dapat mengonfirmasi status billing hanya dari API key, dan tidak mengaktifkan layanan berbayar. Mesin AI lokal membutuhkan server dan model yang dipasang terpisah. Akurasi 100%, seluruh codec, zero latency, HDR fisik, akselerasi pada semua GPU, dan aplikasi bebas cacat tidak dijanjikan. Semua efek playback meninggalkan file asli; ekspor membuat file baru.

Dependensi dan lisensi ada pada THIRD_PARTY.md serta berkas lisensi yang dibundel. Produk belum memiliki code signing, installer dan pembaruan otomatis.

## Editor video multilayer

Buka Cyber80 Hub → Video Studio. Panduan: [VIDEO_STUDIO_ID.md](VIDEO_STUDIO_ID.md). Prompt/spesifikasi pengembangan: [PROMPT_VIDEO_STUDIO_ID.md](PROMPT_VIDEO_STUDIO_ID.md). Lihat batas edisi pertama dan laporan EXE sebelum menganggap setara seluruh fitur Filmora.
