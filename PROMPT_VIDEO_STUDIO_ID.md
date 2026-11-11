# Prompt pengembangan Cyber80 Video Studio

Bertindak sebagai pengembang aplikasi editor video desktop Windows. Kembangkan modul **Cyber80 Video Studio** yang terintegrasi dengan Cyber80 Players. Gunakan Windows Movie Maker sebagai referensi kemudahan penggunaan dan Filmora sebagai referensi alur editing multilayer, tanpa menyalin kode, merek, template, atau aset berlisensi mereka.

Bangun editor non-destruktif yang benar-benar mengomposisikan beberapa layer: background/warna, video utama, overlay video/gambar, judul/grafis, subtitle/lirik, suara/narasi, musik, dan efek suara. Sediakan tambah/urut/hide/lock layer serta mute/solo dan volume audio. File sumber tidak boleh dimodifikasi oleh editing atau ekspor.

Sediakan timeline visual dengan playhead, zoom, scrolling, snapping, pemilihan dan pemindahan klip, trim, split, duplikasi dan penghapusan. Pengaturan klip mencakup source-in, posisi waktu, durasi, speed, posisi X/Y, ukuran, scale, fit/crop, rotasi, opacity dan warna. Tambahkan fade, koreksi warna dasar, chroma key dan keyframe posisi/skala/opacity/volume. Gunakan satu model waktu dan komposisi untuk preview serta ekspor.

Sediakan panel koleksi media, preview visual, properti klip/layer dan pengaturan proyek. Jalankan probing media, pembuatan preview/proxy dan render di background agar antarmuka tetap responsif. Untuk tahap berikutnya, rancang cache proxy per klip, waveform, thumbnail strip, playback timeline real-time, transisi pasangan klip dan nested sequence; jangan menampilkan fitur yang belum bekerja sebagai fitur selesai.

Audio harus dapat dicampur dari beberapa sumber dengan level, pan, fade, mute/solo dan ducking musik terhadap narasi. Sinkronkan audio/video ketika klip dipotong, dipindah atau diubah kecepatannya. Integrasikan impor SRT serta penyalinan subtitle Gemini yang sudah dibuat oleh player, termasuk offset dan sumber yang benar.

Sediakan simpan/buka proyek berversi, undo/redo, autosave, pemulihan dan relink sumber. Dokumentasikan kebijakan sesi privat serta lokasi sumber eksternal. Ekspor offline menjadi file baru dengan pilihan resolusi/aspect ratio/FPS, H.264/AAC dan encoder GPU yang tersedia. Jelaskan bila komposisi tetap memakai CPU. Sediakan progres, pembatalan, penanganan disk penuh, sumber hilang, output terkunci dan perlindungan agar sumber tidak tertimpa.

Audit arsitektur kode terlebih dahulu, gunakan komponen open source yang lisensinya sesuai, dan pertahankan fitur player/browser/download/subtitle yang sudah ada. Jangan menanamkan API key, mengaktifkan billing, atau menjanjikan semua codec, tanpa delay, akurasi 100%, semua situs dapat diunduh, atau bebas bug.

Kerjakan bertahap: fondasi proyek/timeline; komposisi visual dan audio; preview/proxy; subtitle; ekspor; pengujian dan optimasi. Setiap tahap harus memiliki implementasi yang dapat dijalankan dan kriteria penerimaan yang jelas. Uji hasil render nyata—warna/posisi layer, timing, audio, teks, metadata dan hash sumber—serta uji GUI dan EXE Windows. Laporkan fitur yang selesai, bukti uji, batas kemampuan dan pekerjaan berikutnya secara jujur.
