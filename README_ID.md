# LinguaPlayer — proyek Windows x64

Pemutar video berbasis VLC dengan pembuatan subtitle online dari audio memakai Gemini; terjemahan Gemini atau Google Cloud Translation Basic v2. Subtitle dapat disimpan SRT UTF-8 dan digunakan offline di VLC/pemutar lain.

## Status jujur

Paket ini berisi kode sumber lengkap dan skrip build, BELUM berisi EXE hasil build. Disiapkan di Linux; Windows/VLC GUI dan API berbayar belum diuji langsung. Tes otomatis menguji logika subtitle serta integrasi API dengan respons tiruan. Hasil transkripsi, terjemahan dan timestamp AI tidak dijamin 100%. Tidak ada klaim semua format/codec bisa diputar.

## Membuat EXE di Windows 10/11 64-bit

1. Pasang Python 3.12 x64 dari https://www.python.org/downloads/windows/ dan VLC x64 dari https://www.videolan.org/vlc/ .
2. Ekstrak ZIP. Buka PowerShell di folder yang berisi app.py.
3. Jalankan `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`.
4. Jalankan `dist\LinguaPlayer\LinguaPlayer.exe`. Salin/bagikan SELURUH folder LinguaPlayer, karena DLL, plugin VLC, Qt dan FFmpeg diperlukan. Python tidak diperlukan pada komputer tujuan.
5. Alternatif: unggah isi folder proyek ke repository GitHub milik Anda, lalu Actions → Build Windows EXE → Run workflow. Unduh artifact hasil build. Workflow tidak dijalankan otomatis oleh paket ini.

Build memerlukan internet. VLC yang terpasang disalin utuh untuk mempertahankan plugin codec. Build belum signed; penerbitan komersial memerlukan proses pengujian dan code signing tersendiri. Versi dependency yang terpasang saat build dapat dilihat dengan `.venv\Scripts\python -m pip freeze`.

## Memakai aplikasi

1. Buka video lokal dengan tombol Buka video. Dialog menerima semua ekstensi; dukungan sebenarnya mengikuti VLC.
2. Isi Gemini API key dari https://aistudio.google.com/apikey . Model default `gemini-2.5-flash`; ubah ke model audio yang tersedia pada akun Anda bila diperlukan.
3. Pilih bahasa target. Untuk bahasa lain ketik kode bahasa, misalnya `it`, `nl`, `ms` atau `zh-TW`.
4. Isi kamus ejaan: contoh `Pdm. Kezia Sutjiwati; GBI; Nuel Cookies; kasih karunia`. Ini petunjuk kepada Gemini, bukan jaminan ejaan. Jika Google Translate dipakai, kamus ini membantu transkripsi; Basic v2 tidak memiliki glossary terjemahan khusus.
5. Opsional: isi key Google Cloud Translation Basic v2 yang sudah diaktifkan dan memiliki billing/kuota. Jika kosong, Gemini sekaligus menerjemahkan. Google Translate sendiri tidak mengenali suara.
6. Tekan Buat subtitle online. Konfirmasi mengirim audio ke Google. Audio diproses per 45 detik berurutan agar penggunaan memori terbatas. Proses ini bukan live streaming/realtime. Setelah seluruh proses berhasil, hasil muncul di tabel.
7. Koreksi ejaan, istilah, isi dan waktu di tabel. Klik dua kali pada baris untuk menuju adegan. Pilih tampilan bilingual/asli/terjemahan. Offset positif menampilkan subtitle lebih lambat.
8. Ekspor SRT untuk offline. Mode Asli mengekspor transkrip; mode lain mengekspor terjemahan dengan fallback teks asli. SRT bilingual belum tersedia. Simpan proyek JSON untuk mempertahankan kedua teks dan lokasi video; tidak menyimpan key API.
9. Untuk offline, taruh SRT bersama video dengan nama sama (film.mp4 dan film.srt), lalu buka menggunakan VLC. SRT tidak membakar teks ke video. Di aplikasi ini, buka video terlebih dahulu lalu tekan Buka SRT offline. Proyek JSON mempertahankan kedua bahasa; SRT dimuat sebagai teks satu bahasa.

API key hanya disimpan dalam memori selama aplikasi berjalan (atau berasal dari environment GEMINI_API_KEY / GOOGLE_TRANSLATE_API_KEY). Jangan membagikan key atau memasukkannya ke repository. Audio sementara dihapus setelah pekerjaan selesai/gagal. Google menerapkan kebijakan data sesuai layanan/tier Anda.

## Format/codec

VLC mendukung format umum seperti MP4, MKV, AVI, MOV, WebM, MPEG, TS, M2TS, FLV, WMV, VOB, OGV serta berbagai codec seperti H.264/H.265, VP8/VP9, AV1 sesuai build dan perangkat. Performa 4K/8K bergantung hardware. DRM, file rusak, codec proprietari tertentu dan container nonstandar dapat gagal. Subtitle dibuat hanya dari track audio default FFmpeg; pemilihan multiaudio, URL online/YouTube, OCR subtitle, dubbing dan live microphone belum tersedia. "Online" dalam aplikasi ini berarti API transkripsi/terjemahan online, pemutar menggunakan file lokal.

Batas proses saat ini: potongan audio tanpa overlap dapat memisahkan kata pada batas 45 detik; timing diperkirakan Gemini, bukan forced alignment. Pekerjaan yang gagal perlu diulang (belum ada cache/resume). Batal saat panggilan API menunggu timeout maksimal 120 detik; hasil parsial belum disimpan. Video tanpa audio menghasilkan pesan gagal. Harap uji video panjang sebelum penggunaan produksi.

## Ejaan dan akurasi

Untuk hasil baik: audio bersih, daftar nama/istilah, model transkripsi yang tepat, dan tinjauan manusia. PUEBI/EYD dan KBBI dapat menjadi acuan penyuntingan bahasa Indonesia, tetapi tidak terintegrasi otomatis. Pemeriksa tata bahasa atau kamus hanya membantu; makna terjemahan tetap harus diperiksa, khususnya istilah rohani, hukum atau teknis. Google Cloud Translation Advanced v3 menawarkan glossary resmi dengan autentikasi berbeda; belum diimplementasikan dalam aplikasi ini.

## Verifikasi

Jalankan `python -m unittest discover -s tests -v`. Untuk penerimaan Windows, verifikasi MP4/MKV/AVI/WebM, audio dan volume, seek, cancel, key salah/kuota habis, video hening, terjemahan beberapa bahasa, edit, simpan/buka proyek dan SRT offline. API tidak boleh dianggap teruji hanya dari mock test.

## Referensi

- https://ai.google.dev/gemini-api/docs/audio
- https://ai.google.dev/api/generate-content
- https://docs.cloud.google.com/translate/docs/reference/rest/v2/translate
- https://docs.cloud.google.com/translate/docs/authentication
- Lihat THIRD_PARTY.md untuk alat sumber terbuka dan lisensi.
