# Studio Bahasa — Subtitle, Dubbing & Lirik

Buka Cyber80 Hub → Studio Bahasa, atau menu Studio Bahasa → modul terpadu.
Semua pekerjaan berjalan di worker; jendela dapat disembunyikan sambil menonton.
Jangan keluar dari aplikasi sampai selesai atau pembatalan selesai.

## Alur pakai
1. Pilih video/musik lokal. Pilih track audio (0 = pertama), pekerjaan dan bahasa tujuan. Indonesia adalah default.
2. Isi/simpan API key lewat panel Subtitle / AI pemutar. Kunci dipakai di memori, tidak disertakan ke kode, proyek, atau paket.
3. Klik **Buat teks di latar belakang**, pilih nama SRT baru. Potongan suara dikirim ke Gemini untuk mendeteksi bahasa asli dan membuat teks. Opsi attachment video memakai proxy 720p dan mekanisme attachment yang sudah ada. Musik dan lirik memakai audio.
4. Setelah notifikasi selesai, SRT tersimpan dan dapat diedit. Lirik asli juga disimpan sebagai LRC dengan waktu per baris. Periksa kata, terjemahan, nama dan waktu, terutama lagu dengan musik keras.
5. Untuk dubbing, pilih mesin suara/model/suara/campuran lalu **Buat dubbing di latar belakang**. Tidak perlu mengirim video lagi bila SRT sudah tersedia. SRT impor harus sudah berisi bahasa tujuan; tombol dubbing tidak menerjemahkan teks impor lagi.
6. Setelah notifikasi, klik **Putar hasil**. WAV/M4A untuk suara; MP4/MKV untuk video. MKV mode dua track menyimpan dubbing sebagai track pertama dan audio asli sebagai track kedua. Pembuatan video memakai H.264/AAC sehingga memerlukan waktu dan ruang disk.

## Tools yang disertakan
- Gemini REST client: STT/terjemahan yang sudah ada + adapter TTS. Default model suara `gemini-2.5-flash-preview-tts`; model subtitle berbeda dan mengikuti panel pemutar. Model TTS dapat diganti dengan model generateContent TTS yang kompatibel.
- FFmpeg dalam paket: ekstraksi audio, resample, atempo (tanpa mengubah pitch), penempatan suara sesuai waktu, mixing, limiter dan ekspor.
- Adapter Windows System.Speech / SAPI (`sapi_dubbing.ps1`), tanpa API untuk sintesis. Windows harus memiliki suara SAPI sesuai bahasa. Suara OneCore/Narrator belum tentu terlihat oleh SAPI. Jika tidak tersedia, aplikasi menolak, bukan diam-diam memakai suara bahasa lain. Nama suara opsional harus dipilih sesuai bahasa.
- Editor SRT, penyimpanan LRC/SRT, worker latar belakang, pembatalan, notifikasi dan pratinjau VLC.
Tidak perlu memasang Python atau FFmpeg untuk paket EXE hasil build. Tidak ada pip/download program otomatis saat dipakai.

## Campuran dan sinkronisasi
- Voice-over: audio asli diperkecil sepanjang video (bukan deteksi dialog otomatis).
- Ganti semua audio: hanya dubbing; musik/efek asli ikut hilang.
- Instrumental/M&E: pilih sendiri audio musik/efek tanpa dialog yang sudah sinkron, diputar dari awal. Tidak ada pemisahan vokal AI otomatis pada versi ini.
- Dua track: MKV, bisa beralih dubbing/asli melalui pemutar.
Suara yang lebih pendek diberi jeda; suara yang terlalu panjang dipercepat sampai batas tempo pilihan (default 2x). Bila masih tidak muat, proses berhenti dengan nomor cue agar teks bisa diringkas. Ini sinkronisasi waktu, bukan lip-sync atau peniruan suara aktor. Suara TTS bukan suara nyanyian.

## Biaya, privasi dan batas
Gemini 2.5 Flash Preview TTS memiliki Free Tier menurut dokumentasi Google, tetapi akses/kuota/ketersediaan tergantung proyek. Aplikasi tidak menyalakan billing, tidak berpindah layanan berbayar, dan berhenti pada penolakan/kuota. Proyek yang telah mengaktifkan billing tetap tunduk tarif Google; aplikasi tidak dapat memaksa proyek berbayar menjadi gratis. Pilih proyek tanpa billing untuk menghindari biaya API, atau gunakan SRT yang sudah ada dan suara Windows offline.
Audio/teks dikirim ke Google hanya ketika tombol online ditekan. Dubbing Windows dari SRT berjalan lokal. Teks hasil dipertahankan di editor sampai aplikasi ditutup; simpan edit sebelum keluar. Pekerjaan audio chunk yang dibatalkan harus dimulai lagi; attachment mengikuti mekanisme checkpoint sebelumnya bila dipakai lewat menu lama.
Tidak ada jaminan akurasi sempurna, bahasa semua tersedia, hasil real-time atau tanpa delay. Tidak ada jaminan suara identik, diarization multi-aktor otomatis, penghapus musik otomatis, atau karaoke per kata. Model TTS/kuota dapat berubah.

## Verifikasi
Unit dan uji ekspor menggunakan audio sintetis: posisi suara, jeda, durasi, WAV/M4A/MP4/MKV, pembatalan, penolakan cue terlalu panjang dan sumber tidak berubah. Uji yang sama dimasukkan ke EXE Windows. CI tidak memiliki API key sehingga **kualitas dan akses Gemini TTS langsung tidak diuji di CI**. Status tersebut ditulis apa adanya di HASIL_UJI_WINDOWS.json; bukan dianggap PASS.

Referensi tools: https://ai.google.dev/gemini-api/docs/generate-content/speech-generation
https://ai.google.dev/gemini-api/docs/pricing
https://ffmpeg.org/ffmpeg-filters.html
https://learn.microsoft.com/dotnet/api/system.speech.synthesis.speechsynthesizer

## Voice cloning gratis — OpenVoice V2
Centang **Pertahankan karakter suara asli**, klik **Pasang Voice Tools gratis** satu kali (Windows 64-bit, internet, ruang beberapa GB). Installer mengunduh runtime Python portable, PyTorch CPU, kode OpenVoice MIT pada commit tetap dan model converter V2 resmi. Tidak mengubah Python sistem; tidak memerlukan akun/API OpenVoice. Tunggu tulisan Selesai. Tools terpisah dari EXE agar paket utama tetap ringan. Untuk memindahkan tools ke PC lain salin seluruh folder VoiceTools, lalu pilih folder tersebut.

Pilih sampel suara satu pembicara yang bersih, 1–30 detik (ideal 6–15 detik), bahasa apa pun, tanpa musik keras. Kosongkan file referensi untuk mengambil rentang dari video sumber. Sampel tetap memakai satu karakter suara untuk seluruh dubbing. Opsi **sampel otomatis per dialog** mengambil suara dari interval masing-masing cue; cue kurang dari 1 detik ditolak, dialog bertumpuk/musik/lebih dari satu pembicara dapat menurunkan kualitas. Tidak ada deteksi identitas aktor otomatis. Sampel eksternal mengalahkan opsi per dialog.

Suara bahasa tujuan dibuat Gemini/SAPI terlebih dahulu, lalu OpenVoice mentransfer karakter suara sampel secara lokal, kemudian waktunya disinkronkan. Cloning tidak menerjemahkan teks. Dukungan bahasa tetap mengikuti TTS dasar; bukan klaim semua bahasa dunia. Bahasa Indonesia default. Kemiripan, aksen, emosi, serta kualitas suara Indonesia harus diperiksa sendiri. Gunakan rekaman yang Anda berhak gunakan. Sampel/embedding sementara dihapus ketika pekerjaan selesai/batal; tidak diunggah untuk tahap cloning. Tidak ada biaya API cloning, tetapi TTS Gemini tetap mengikuti kuota/tarif proyek. SAPI + SRT + OpenVoice dapat berjalan offline bila suara sesuai bahasa sudah terpasang.

Tools CPU dapat lambat; tidak membutuhkan GPU. Model/config resmi diunduh melalui HTTPS dan hash lokal dicatat di installation.json; kode sumber dipatok ke commit. Worker memuat tensor checkpoint dengan weights_only=True. Adapter ini tidak mengunduh model watermark tambahan; hasil diberi judul audio Cyber80 Dubbing. Ini bukan klaim watermark audio atau deteksi AI.

Sumber: https://github.com/myshell-ai/OpenVoice (MIT), commit 74a1d147b17a8c3092dd5430504bd83ef6c7eb23. OpenVoice V2 TTS native hanya enam bahasa; Cyber80 memakai converter lintas bahasa di atas TTS Gemini/SAPI, bukan mengklaim TTS native OpenVoice mendukung semua bahasa.
