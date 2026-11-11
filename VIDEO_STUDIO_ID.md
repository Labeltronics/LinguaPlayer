# Cyber80 Video Studio — Editor multilayer

Buka **Cyber80 Hub → Video Studio • Editor multilayer**. Film aktif dapat diimpor otomatis. Modul ini bekerja offline; tidak memanggil layanan AI berbayar untuk render.

## Alur cepat

1. Impor video, gambar, suara/narasi dan musik. File yang diimpor ditambahkan berurutan; double-click koleksi untuk menambahkannya lagi pada playhead.
2. Pilih layer. Layer ditumpuk sesuai urutan daftar **dasar → teratas**; gunakan Naikkan/Turunkan layer untuk mengatur urutan komposisi.
3. Klik klip untuk membuka properti. Drag bagian tengah untuk menggeser, drag ujung untuk trim. Ctrl+scroll memperbesar/memperkecil timeline; snapping menempel ke playhead/batas klip.
4. Gunakan **Split di playhead**, duplikat, hapus, posisi/durasi/source-in, speed 0,1–10×, fit/crop/stretch, X/Y, ukuran, skala, rotasi, opacity, warna, brightness/contrast/saturation, blur dan chroma key. Klik **Terapkan properti klip**.
5. Tambah warna/latar, judul, atau SRT. **Subtitle AI film aktif** menyalin cue dan offset dari player utama; pastikan filmnya cocok. Teks dapat diedit pada panel properti. Track SRT memakai posisi bawah tetap dan ukuran teks; animasi posisi/opacity memakai judul teks, bukan track SRT.
6. Untuk animasi, atur playhead di dalam klip, isi properti X/Y/skala/opacity/volume, lalu **Tambah keyframe di playhead**. Double-click keyframe untuk kembali ke waktunya. Interpolasi linear; maks. 200 keyframe/klip.
7. Atur volume klip/layer, pan, fade audio, mute/solo. **Pengaturan proyek → Audio ducking** menurunkan layer musik saat layer Suara/narasi bersuara. Audio bawaan video juga dapat dimatikan. Sumber tanpa audio tidak dapat dipaksa memiliki audio.
8. **Perbarui preview frame** memproses komposisi pada playhead. **Render & putar proxy** membuat MP4 maksimum 640×360 untuk playback VLC. Perubahan setelah render memerlukan preview/proxy baru; ini bukan playback timeline multistream real-time.
9. Simpan proyek `.cyber80.json`. Sumber tetap file eksternal dengan path absolut. Gunakan Relink jika dipindah; periksa kembali durasi media pengganti. Undo/redo menyimpan maksimal 100 keadaan proyek.
10. **Ekspor MP4** menghasilkan komposisi H.264/AAC. Atur format proyek, FPS dan warna latar sebelum render; mendukung Full HD/4K dan orientasi vertikal. Encoder CPU tersedia; NVENC/QSV/AMF memerlukan hardware/driver cocok. Komposisi/effect tetap memakai CPU; pilihan encoder bukan akselerasi GPU seluruh timeline.

## Penyimpanan dan keamanan sumber

Render memakai file sementara dan commit atomik. Hasil ditolak bila menimpa sumber atau file tujuan berubah selama render. Pembatalan menghapus hasil parsial. Proyek tidak menanamkan API key.

Autosave tiap 30 detik hanya bila penyimpanan aplikasi aktif dan sesi player tidak privat. **Pulihkan autosave** membuka checkpoint terakhir. Simpan proyek manual sebelum keluar; media tidak disalin ke dalam JSON. Tutup aplikasi menunggu impor/render berhenti dan meminta penyimpanan bila perlu.

## Batas edisi pertama

- Maksimum 32 layer, 128 klip, durasi proyek 24 jam, dimensi genap sampai 4096×4096 dan FPS 1–120 melalui model proyek. UI menyediakan FPS umum termasuk 23,976/29,97/59,94 sebagai pecahan.
- Preview frame maksimum 640×360. Proxy harus dirender terlebih dahulu. Belum ada playback timeline real-time seperti Filmora, cache proxy per klip, waveform audio penuh, thumbnail strip timeline, nested sequence, multicam, motion tracking atau kolaborasi.
- Gambar diam PNG/JPEG/BMP/WebP/TIFF dibaca melalui FFmpeg. Codec sumber mengikuti decoder FFmpeg; durasi sumber harus dapat dibaca. Tidak menjanjikan semua codec atau DRM.
- Fade masuk/keluar dan opacity tersedia; belum ada katalog transisi Filmora, cross-dissolve khusus pasangan klip, template berlisensi atau plugin pihak ketiga.
- Teks memakai Arial milik Windows atau DejaVu Sans pada lingkungan uji. Layout font dan subtitle perlu diperiksa pada hasil preview, khususnya naskah kompleks/RTL.
- Autosave/history memakai snapshot, bukan database transaksi; jumlah klip dan keyframe dibatasi untuk mengendalikan RAM. Source probing, render dan preview berjalan di worker, tetapi proyek besar/4K tetap dapat lambat.
- TV/GPU fisik dan kualitas editor pada proyek berjam-jam belum diverifikasi. Batasan modul sebelumnya tetap berlaku.

## Pengujian

Tes model/render mencakup split, undo/redo, JSON, frame boundary, layer terkunci, rentang sumber, keyframe, penolakan input tidak valid, warna piksel komposisi, audio nyata, ducking, title/subtitle, still preview, speed, chroma/blur/crop, pembatalan dan hash sumber. Tes UI mencakup properti, timeline, simpan dan preview asinkron.

`HASIL_UJI_WINDOWS.json → playback.video_studio` mencatat pengujian EXE yang benar-benar berjalan: impor video/gambar/audio, split/undo, proyek, preview frame, komposisi MP4 beserta audio, teks dan subtitle, pemutaran VLC, serta keutuhan sumber. Pengujian DNS hanya membaca konfigurasi; tidak mengubah DNS mesin build.

## Layer Green Screen

Klik **Layer Green Screen** untuk menambah layer khusus di atas video biasa dan di bawah judul/subtitle. Pilih layer itu, lalu **Impor media** berupa video/gambar berlatar hijau. Chroma key langsung aktif dengan warna #00ff00, toleransi 0,12 dan kehalusan tepi 0,05. Letakkan video/gambar/latar pengganti pada layer di bawahnya.

Untuk klip yang sudah ada, pindahkan ke layer Green Screen melalui properti atau drag timeline. Preset diterapkan saat pindah. **Preset Green Screen** mengaktifkan ulang nilai awal pada klip video/gambar yang terpilih. Gunakan **Pilih warna kunci** untuk hijau lain atau blue screen, kemudian sesuaikan **Toleransi warna kunci** dan **Kehalusan tepi**. Klik Terapkan properti klip, perbarui preview atau render proxy, lalu ekspor MP4.

Layer tetap mendukung posisi, ukuran, keyframe, trim dan audio video. Perubahan disimpan dalam proyek dan dapat di-undo. Ini chroma key berdasarkan warna, bukan penghapus background AI; pencahayaan tidak rata, bayangan, rambut dan pantulan hijau dapat memerlukan penyesuaian. Belum ada despill khusus atau color picker dari piksel preview.

## Template kolase, slideshow, opening dan ending

Klik **Template foto / opening**. Pilih kolase 2/4/6/9 foto, slideshow dengan zoom halus, opening, ending, lower third, atau kartu kutipan. Pilih banyak foto dan atur urutan lewat Foto ↑/↓. Isi judul, keterangan, warna latar, durasi, dan logo opsional untuk opening/ending.

Pilih akhir proyek, awal (menggeser seluruh klip yang ada), atau playhead (overlay). Opening menyarankan posisi awal; ending menyarankan akhir. Layer yang terkunci harus dibuka sebelum seluruh timeline digeser. Kolase membuat halaman tambahan bila foto melebihi jumlah kotak; durasi adalah per halaman. Slideshow memakai durasi per foto dan fade ke latar, bukan cross-dissolve berpasangan.

Template menjadi klip/layer biasa yang dapat diubah, disimpan dan di-undo. Foto kolase memakai cover/crop awal; ubah fit menjadi contain bila ingin seluruh foto terlihat. Musik ditambahkan lewat impor audio ke layer Musik. Template tidak mengunduh aset atau musik berlisensi. Batas proyek 32 layer/128 klip tetap berlaku; satu template menambah tiga layer. Tidak ada video stock atau musik bawaan.
