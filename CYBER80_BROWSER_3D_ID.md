# Cyber80 Players — Browser, Download, Cutting, Stereo TV & Hard Subtitle

Pembaruan 12 November 2026. Tidak ada API key ditanamkan. Semua modul sebelumnya tetap tersedia. Daftar ini membedakan kemampuan aktual dari batas implementasi.

## Alur utama

**Cyber80 Hub → Browser multimedia → putar media di situs → Media terdeteksi → Download media → Download Manager → Putar / Playlist → Cutting visual / Subtitle AI → Gabungkan subtitle → Simpan video baru.**

Browser menggunakan Qt WebEngine/Chromium dalam proses renderer terpisah. Browser bukan mesin VLC: codec web yang tersedia mengikuti build Qt. WebM/WAV diuji; jangan menganggap semua video yang bisa diputar VLC juga dapat diputar langsung dalam browser. `Putar di Cyber80` pada panel media membuka preview VLC terpisah untuk URL langsung tanpa cookie/Authorization; untuk sumber bersesi login, unduh terlebih dahulu. Tidak ada Widevine/DRM bypass.

## Browser dan deteksi media

- Tab, address/search bar, kembali/maju/refresh, bookmark, riwayat tanpa query URL, profil privat off-the-record, penghapusan cookie/cache/riwayat, dan fullscreen HTML5.
- Browser normal dipisah per jendela player. Bookmark hanya disimpan jika pengguna memilihnya. Mode privat tidak menyimpan riwayat/bookmark aplikasi; unduhan yang sengaja disimpan tetap menjadi file lokal.
- Deteksi dari request jaringan (Media/XHR), ekstensi, elemen video/audio/source, dan pemeriksaan header respons/MIME. Probing dibatasi untuk menghindari membanjiri server. URL duplikat ditekan, segmen m4s dan nama chunk TS umum tidak memenuhi panel.
- MIME, ukuran bila server memberikannya, situs sumber dan pilihan kualitas manifest ditampilkan. Media baru dapat muncul setelah tombol Play pada situs ditekan.
- Deteksi belum memakai seluruh response-body/CDP, tidak dapat mengekstrak semua blob/MSE, tidak menjamin dapat membedakan iklan dari media utama, dan tidak menjamin semua situs. Tidak ada bypass paywall, CAPTCHA, enkripsi atau DRM.
- Sesi cookies dipilih berdasarkan domain/path/HTTPS. Download URL langsung menggunakan header yang tertangkap di memori; kredensial dihapus pada redirect lintas origin, dan downgrade HTTPS→HTTP ditolak. Cookie/Authorization tidak disimpan dalam JSON antrean atau log aplikasi. Console JavaScript situs tidak diteruskan ke log aplikasi.

## Download Manager

- Antrean, 1–4 unduhan bersamaan, prioritas, batas kecepatan total, ukuran/progres/kecepatan/ETA bila tersedia, notifikasi selesai, pause/resume, cancel dan retry terbatas.
- Mode 1–4 koneksi per file. Paralel hanya digunakan untuk file dengan ukuran ≥1 MiB, ETag kuat dan respons Range yang konsisten. Jika server tidak mendukungnya, aplikasi memakai satu koneksi.
- Resume byte menggunakan If-Range dan ETag/Last-Modified. Respons 200 mengganti partial dari awal, bukan menambahkannya. Perubahan validator mereset partial. Tanpa validator, resume aman dimulai ulang. HTTP403 tidak diulang otomatis.
- Output disimpan ke file sementara unik. File final diganti atomik setelah lengkap/checksum cocok. Jika tujuan berubah sejak tugas dibuat, commit ditolak agar file lain tidak tertimpa. Sumber lokal tidak diubah.
- Verifikasi SHA256 opsional melalui tombol SHA256. Pemeriksaan ruang disk, nama file aman, penanganan URL kedaluwarsa dan tombol perbarui URL tersedia.
- Metadata antrean tidak menyimpan URL sumber. URL sumber tugas nonprivat disimpan melalui Windows Credential Manager, lalu dihapus setelah selesai. Jika URL terlalu panjang/tidak bisa disimpan, pengguna perlu memasukkannya kembali sesudah restart. Cookie/Authorization tidak dipulihkan otomatis: login ulang dan gunakan **Hubungkan sesi** atau deteksi ulang media.
- HLS: VOD selesai dengan ENDLIST, master/varian kualitas, audio eksternal, TS atau fMP4/map. Tidak mendukung live tanpa batas, AES/enkripsi, low-latency parts, byte-range, atau master bertingkat.
- DASH: static satu Period, Representation BaseURL, SegmentList atau SegmentTemplate/Timeline yang didukung; video dan audio dipilih lalu digabung lokal. Dynamic/multi-period, ContentProtection, byte-range tertentu dan template di luar subset tidak didukung.
- FFmpeg menggabungkan segmen yang sudah didownload. HLS hanya memakai protokol file lokal saat remux; URL/auth tidak diberikan sebagai header global ke FFmpeg.
- Unduhan native browser menangani aksi download dari halaman/konteks browser dengan sesi Chromium. File disimpan dalam folder sementara lalu dipindah setelah sukses. Resume native hanya selama sesi browser hidup; setelah restart harus dimulai lagi dari halaman. Blob MSE tidak otomatis menjadi satu file yang dapat didownload.
- **Bersihkan daftar selesai** hanya menghapus metadata antrean, bukan file hasil. Tidak ada file hasil yang dijalankan otomatis.

## Cutting visual video dan musik

Buka media lokal → **Cyber80 Hub → Cutting visual**. Preview VLC memiliki video/timeline sendiri, penanda awal/akhir dengan tiga angka desimal, tombol ambil posisi saat ini, lompat ke awal, frame maju, loop A–B, dan daftar banyak potongan. Preview awal mute agar tidak bercampur dengan suara player utama.

Ekspor pilihan atau semua potongan secara berurutan. Video menjadi MP4 H.264/AAC; audio menjadi M4A/AAC. Ini re-encode, bukan editor multitrack atau stream-copy lossless. FFmpeg mengeksekusi timestamp pilihan, tetapi ketelitian visual preview/seeking tetap mengikuti decoder/keyframe. Pembatalan tidak menimpa sumber.

## 3D TV tanpa anaglyph

**Cyber80 Hub → 3D / 4D Cinema** menyediakan:
- Input 2D→stereo dengan estimasi depth AI MiDaS; SBS half/full atau TB half/full asli.
- Output SBS half/full, TB half/full, row/column interlaced, checkerboard, atau satu mata.
- Kekuatan depth AI 0–6% lebar, bidang layar/pop-out 0–1, konvergensi ±100px, tukar mata, dan stabilisasi depth. Untuk sumber stereo asli, kedalaman asli berasal dari pasangan mata; konvergensi hanya menggeser bidang pandang, bukan memperkirakan ulang geometri stereo.
- MiDaS v2.1 small ONNX dibundel, MIT, checksum dipatok. CPU tersedia; DirectML dapat dipilih bila runtime/GPU/driver mendukungnya. Warp dan packing stereo memakai CPU, bukan renderer GPU end-to-end. Opsi provider bukan pengukuran aktivitas GPU fisik.
- Preview mengambil frame terbaru tanpa antrean frame tak terbatas; ukuran maksimum 960×540. Pemrosesan AI dapat terlambat/drop frame dan membutuhkan penyesuaian sinkron audio manual pada Audio Studio. Bukan jaminan real-time 4K/10×.
- Ekspor stereo MP4 menggunakan resolusi sumber dan FPS sumber. Format full menggandakan salah satu dimensi; half membagi resolusi per mata. Proses AI setiap frame bisa lama dan boros RAM pada sumber besar.
- TV/headset harus mendukung format stereo yang dipilih dan diatur sesuai inputnya. SBS pada monitor biasa memang terlihat dua gambar. Interlaced/checkerboard perlu pemetaan piksel, orientasi dan skala tampilan yang benar; kalibrasi TV fisik belum diverifikasi. HDMI frame-packing 3D otomatis, shutter-glasses sync, OpenXR/VR dan Dolby 3D belum tersedia.
- AI memperkirakan kedalaman per area gambar, bukan sekadar menggeser satu bidang 2D. Namun, geometri/area tersembunyi tidak dapat dipulihkan secara pasti. Reprojection menggunakan sampling dan pengisian tepi sederhana, sehingga smear/artefak dan kesalahan depth tetap mungkin terjadi.

## Arti modul 4D

Cue 4D hanya profil/pratinjau waktu efek (getaran, angin, gerak, cahaya), dengan durasi dan intensitas, impor/ekspor JSON, dan indikator mengikuti waktu film. Tidak mengirim perintah ke kursi, aktuator, lampu atau perangkat fisik. Ini bukan format gambar berdimensi empat, dan tidak diklaim sebagai sistem teater 4D fisik.

## Speed, scroll, zoom, capture

- Speed 0,1×–10×; penerimaan dan kualitas audio tergantung decoder/perangkat/media. Time-stretch bukan jaminan audio tetap sempurna pada ekstrem.
- Scroll di area video utama: atas maju 5 detik, bawah mundur 5 detik. **Cyber80 Hub → Atur scroll seek** mengubahnya menjadi 1–300 detik dan menyimpannya. Scroll browser/playlist/pengaturan tidak dijadikan seek. Windows memakai hook yang hanya mengonsumsi wheel di persegi video milik jendela Cyber80 yang sedang foreground; hook dilepas saat ditutup.
- **Zoom / Speed / Capture**: 0,10%–1000%, Zoom+/−, reset 100%, interpolasi Full HD/4K. Di mode zoom, frame sumber dipertahankan sampai maksimum 4K, lalu diproses/display via CPU. Ini bukan AI super-resolution; video beresolusi rendah tetap tidak memperoleh detail yang hilang. Beban CPU/RAM dan dropped frame dapat meningkat.
- Capture tampilan menyimpan viewport zoom/stereo, sedangkan capture frame sumber menyimpan frame dari pemutar. Subtitle overlay terpisah belum dibakar ke screenshot viewport; gunakan ekspor hard subtitle untuk teks permanen.

## Hard subtitle dan video lirik

Setelah subtitle tersedia, pilih **Gabungkan subtitle film aktif → Simpan video baru**. Untuk hasil attachment yang berasal dari media lain, gunakan **Gabungkan subtitle attachment terakhir** atau tombol pada notifikasi. Sumber dan cue hasil attachment ditangkap terpisah agar tidak tertukar dengan film yang sedang dibuka.

Video diekspor MP4 dengan subtitle dibakar permanen. Musik diekspor menjadi video lirik berlatar warna 1920×1080 dengan teks tersinkron. Ini teks per cue, belum karaoke per kata atau pembuat music video AI. Offset subtitle film aktif ikut diterapkan; cue attachment memakai timestamp sumbernya. Bahasa mengikuti hasil/editor yang dipilih, terjemahan jika ada atau ucapan asli jika tidak ada.

Pilih lokasi hasil sebelum proses. Terdapat pembatalan dan notifikasi serta tombol buka folder. Hasil ini file lokal baru, bukan unggahan publik. Efek zoom/3D/EQ UI tidak otomatis ikut terbakar pada ekspor hard subtitle biasa; ekspor stereo adalah alur terpisah.

## Bukti dan batas pengujian

88 tes otomatis lokal mencakup suite sebelumnya ditambah HTTP server sungguhan untuk resume/paralel/fallback, redirect/cookie isolation, HTTP403, checksum, target berubah, disk penuh, HLS dan DASH nyata lalu remux FFmpeg, kontrol speed/scroll/zoom, trim range, stereo packing dan inference model MiDaS CPU asli. Subtes FFmpeg mencakup hard subtitle, video lirik, pemotongan video/audio dan alat sebelumnya.

Laporan Windows di HASIL_UJI_WINDOWS.json mencatat tes EXE yang benar-benar dijalankan, termasuk browser lokal, deteksi MIME/DOM, pemutaran WebM/WAV, download HTTP/native Chromium, cutting visual, zoom/capture/reset, dan preview/ekspor stereo MiDaS. Hanya klaim PASS yang tercatat boleh dianggap teruji di build tersebut. Browser cloud Linux tanpa display GPU mengalami masalah renderer; hasil itu tidak dipromosikan sebagai pengujian browser sukses.

Suite otomatis tidak mengunjungi akun/situs pribadi atau melakukan inferensi Gemini. Uji langsung terbatas dengan key pengguna dijelaskan terpisah di bagian verifikasi Gemini di bawah. GPU fisik, TV 3D fisik, headset, HDR, kualitas terjemahan film nyata, seluruh situs/codec, pembatalan koneksi seketika dan stress 24 jam belum diverifikasi. Konektivitas socket aktif dapat menunggu timeout hingga 20 detik pada downloader dan hingga 180 detik pada Gemini.


## Preferensi pencarian dan akses jaringan

Google menjadi pencarian default. Checkbox **Google SafeSearch: Off** menambahkan `safe=off` pada pencarian dan menyesuaikan URL pencarian Google yang didukung. Ini preferensi pengguna, bukan bypass kebijakan akun/administrator; rewrite dibatasi agar tidak berputar tanpa akhir jika Google memaksakan filter. Tidak ada filter konten tambahan dari aplikasi.

**Proxy / akses jaringan** mendukung proxy sistem/VPN Windows, tanpa proxy, atau proxy HTTP/HTTPS CONNECT milik pengguna dengan username/password opsional. Konfigurasi berlaku pada browser dan koneksi downloader baru dalam proses ini; bukan per-tab/per-profil. Penyimpanan konfigurasi hanya melalui Windows Credential Manager bila dipilih. Tidak disediakan proxy/VPN publik gratis bawaan, SOCKS5, Tor, atau jaminan semua situs diblokir akan terbuka. Pengaturan tidak menonaktifkan verifikasi sertifikat HTTPS, sandbox Chromium, DRM atau kontrol akses situs. Mengubah proxy tidak memindahkan koneksi yang sudah aktif; muat ulang atau mulai ulang tugas yang bersangkutan.


## Verifikasi Gemini asli terbaru

Pemeriksaan metadata API berhasil dan model gemini-3.5-flash-lite tersedia. Transkripsi suara sintetis Inggris 4,23 detik ke Indonesia berhasil, dua cue SRT tersimpan, 22,71 detik termasuk retry (dua request). Uji attachment pertama mendapat HTTP503 layanan sibuk; uji ulang attachment berhasil dalam 65 detik, tanpa memakai fallback audio. Lihat GEMINI_LIVE_TEST_REPORT.json dan examples/ untuk hasil asli tanpa API key. Tidak ada film/audio pribadi pengguna yang diunggah. Uji langsung ini menggunakan kuota proyek Free Tier yang disebutkan pengguna; aplikasi tidak mengaktifkan billing.

Satu respons attachment salah memberi label bahasa sumber `id` walau transkripnya Inggris. Prompt kini menegaskan bahwa kode bahasa harus milik suara asli. Pemeriksa teks offline meninjau label yang kosong/unknown/sama dengan bahasa target untuk teks cukup panjang dan keyakinan ≥98%; hasil tidak dijamin benar untuk semua bahasa, teks pendek atau campuran. Transkrip/terjemahan mentah dalam laporan tetap dipertahankan, tidak disamarkan sebagai output model yang sempurna.

Fallback audio dapat dinonaktifkan di panel attachment. Saat aktif, kegagalan sementara 408/500/502/503/504 atau timeout pada jalur video dapat beralih ke audio dari video yang sama, model tetap sama. Kuota tambahan mungkin terpakai; tidak ada model/layanan berbayar otomatis. Fallback tidak dijalankan untuk 403 atau kuota 429. Uji fallback menggunakan server/response tiruan; uji langsung attachment terakhir berhasil pada jalur video sehingga fallback tidak diperlukan. Server Google tetap dapat sibuk, dan latensi tersebut bukan jaminan real-time/tanpa delay.
