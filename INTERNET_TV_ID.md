# Internet TV / IPTV

Buka Cyber80 Hub → Internet TV / IPTV → Muat katalog dunia gratis. Katalog diperbarui dari API publik IPTV-org saat tombol ditekan, bukan IP statis yang cepat kedaluwarsa. Cari nama saluran, filter negara/kategori, tandai favorit, lalu pilih Putar. Memerlukan internet; tidak memerlukan antena. Tidak menjamin semua saluran dunia, semua saluran selalu aktif, atau tanpa batas wilayah. Saluran premium/DRM tidak dibuka.

Katalog bawaan mengabaikan entri yang ditandai NSFW. Tidak disediakan direktori pornografi. Playlist M3U/M3U8 saluran lokal atau URL HTTP/HTTPS sendiri dapat diimpor untuk akses yang Anda berhak gunakan. Manifest HLS satu saluran berbeda dari playlist saluran dan ditolak pada impor. URL dengan nama pengguna/sandi, RTSP/UDP, opsi header VLC/Kodi khusus dan DRM tidak didukung pada modul impor ini. Beberapa saluran memerlukan situs/aplikasi resmi. URL playlist tidak disimpan otomatis; favorit hanya menyimpan hash identitas saluran.

PIN awal sesuai permintaan pemilik, disimpan sebagai PBKDF2-HMAC-SHA256 dengan salt, tidak sebagai angka terbaca di source/settings. Kategori impor bertanda 18+/adult/dewasa disembunyikan; masukkan PIN untuk membuka, atau ganti PIN dari panel. Setelah lima kesalahan ada jeda 30 detik. Tutup panel/kunci kembali untuk mengunci sesi dan menghentikan tayangan. Ini kontrol lokal berdasar metadata, bukan pengenal isi video: saluran salah kategori bisa lolos dan pengguna komputer yang dapat mengganti kode/settings dapat melewati kontrol lokal.

## Cari program / EPG
Impor panduan XMLTV (.xml/.xmltv/.gz) yang Anda peroleh dari penyiar/sumber berizin. tvg-id dalam M3U harus sama dengan channel ID XMLTV. Pencarian juga mencocokkan judul acara, dan tabel menampilkan sekarang/berikutnya dengan waktu lokal. Katalog publik tidak menyertakan jadwal lengkap seluruh dunia. File XMLTV maksimum 32 MiB setelah decompression; deklarasi DTD/entity ditolak. Tampilan maksimum 3000 baris sekaligus; gunakan filter untuk mempersempit.

## Subtitle online TV (tanpa dubbing)
Isi Gemini API key dan model di panel Subtitle / AI pemutar. Putar saluran, pilih kode bahasa subtitle (default id), lalu Aktifkan subtitle online. FFmpeg membuka koneksi terpisah untuk mengambil suara terus-menerus dalam potongan 15 detik, Gemini mendeteksi bahasa dan menerjemahkan. Subtitle tampil pada area teks di bawah video. Suara TV asli tetap diputar; tidak ada dubbing TV.

Subtitle **tertunda**, bukan teks yang sinkron sempurna dengan siaran saat itu. Status menunjukkan perkiraan jeda minimal pengambilan audio + respons API. Ketika API tertinggal, segmen lama dilewati agar tidak terus menambah antrean; bagian dialog dapat hilang. Kuota/akses dan biaya mengikuti proyek Gemini seperti subtitle biasa; aplikasi tidak mengaktifkan billing atau pindah layanan berbayar. Proyek tanpa billing diperlukan bila ingin menghindari tagihan API. Hentikan subtitle untuk menghentikan analisis/koneksi suara. Permintaan aktif dapat menunggu timeout. Pergantian saluran menunggu worker lama selesai. Siaran yang menolak koneksi kedua atau tidak didukung FFmpeg dapat diputar VLC tetapi subtitle tidak tersedia.

Uji parser, metadata, filter, XMLTV/gzip, PIN dan ekspor dubbing berjalan tanpa kunci. Ketersediaan saluran dan terjemahan live Gemini perlu diuji pada jaringan/proyek pengguna; tidak dianggap lolos hanya berdasarkan unit test. Tidak ada perekaman otomatis atau penyimpanan riwayat siaran. Segmen audio sementara dihapus ketika subtitle berhenti.

Sumber katalog: https://github.com/iptv-org/api dan https://github.com/iptv-org/iptv — tautan saluran publik dari komunitas; daftar bukan jaminan lisensi atau ketersediaan setiap saluran.
