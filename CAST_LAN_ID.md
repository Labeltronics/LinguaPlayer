# Cast / Mirroring ke perangkat pada jaringan yang sama

Tombol **Cast** tersedia pada bar pemutar video dan **Cast / Mirroring** pada Internet TV. Pilih alamat IPv4 Wi-Fi/Ethernet komputer yang satu jaringan dengan penerima. Bila ada VPN/beberapa adapter, pilih alamat yang dapat dijangkau penerima.

## Pilihan penerima
- **Chromecast / Google TV / Android TV dengan Google Cast**: klik Cari Google Cast / DLNA, pilih perangkat, lalu Cast ke perangkat. Android TV yang tidak menyediakan Cast receiver memerlukan aplikasi penerima yang cocok.
- **Smart TV dengan DLNA MediaRenderer**: aktifkan penerima media jaringan TV. Aplikasi mencari perangkat via SSDP lalu mengirim AVTransport SetAVTransportURI/Play. Bukan semua Smart TV mendukung protokol yang sama.
- **HP Android/iPhone, tablet, komputer atau TV dengan browser**: klik Buat tautan HP/browser, salin alamat lalu buka pada browser penerima dan tekan Play. Tidak perlu aplikasi Cyber80 pada HP. Dukungan codec/HLS bergantung browser; ini pemutaran media, bukan remote desktop.
- **Mirroring tampilan Windows**: tombol Mirroring Windows membuka panel Win+K. Pilih penerima Miracast yang kompatibel. Ini mencerminkan tampilan Windows termasuk subtitle, zoom dan efek pemutar. Membutuhkan dukungan Miracast di PC, driver dan penerima; pemilihan/pairing dilakukan melalui panel Windows.

Google Cast dan DLNA mengirim media asli, bukan gambar layar. Tidak ada transcoding otomatis atau jaminan semua format yang bisa dimainkan VLC didukung TV/HP. Bila ditolak, ekspor MP4 H.264/AAC melalui Video Studio, lalu Cast file baru. Gunakan format audio yang didukung penerima. Jenis MIME dapat dipilih manual jika URL siaran tidak memiliki ekstensi. DLNA pada modul ini memulai dari awal; Google Cast mencoba mulai dari posisi pemutar ketika dialog dibuka. Setelah Cast, kontrol perangkat terpisah dari pemutar lokal. Play/Pause/Stop tersedia di dialog.

Subtitle file yang tersedia saat dialog dibuat dibagikan sebagai WebVTT ke browser/Google Cast. Perubahan teks sesudahnya memerlukan Cast ulang. Subtitle live TV ditampilkan pada PC; untuk mencerminkannya ke TV gunakan Miracast. DLNA tidak menjamin dukungan subtitle eksternal. Tidak ada dubbing Internet TV.

## Jaringan dan privasi
Berbagi hanya dimulai setelah tombol tautan/Cast ditekan. Server HTTP hanya melayani satu media terpilih dan VTT, tanpa daftar folder, dengan token acak per sesi dan pembatasan alamat privat/loopback. Tautan dapat dipakai siapa pun pada LAN yang mengetahuinya; jangan sebarkan atau forward port router. Tidak ada UPnP port forwarding. Hentikan Cast/tutup dialog/keluar aplikasi untuk menutup server. Perintah Stop ke perangkat bersifat best effort bila perangkat terputus. URL saluran langsung yang sudah diterima TV berada di luar kendali server komputer.

Izinkan aplikasi melalui Windows Firewall pada profil jaringan privat bila Windows meminta. Aplikasi tidak mematikan firewall/TLS. Wi-Fi guest/AP isolation/VPN/firewall dapat menghalangi penemuan atau pemutaran. Google Cast juga dapat memerlukan akses internet pada perangkat. Tidak semua browser TV mendukung video live/HLS. Konten premium/DRM atau yang membutuhkan cookie aplikasi khusus tidak dibuka melalui Cast.

Parental control Internet TV berlaku sebelum mengirim media. Mengunci kembali mengirim Stop dan menutup tautan Cast yang dibuka dari panel TV, tetapi bukan DRM atau kontrol permanen atas perangkat lain. Penerima/playlist eksternal tetap perlu parental control sendiri.

## Verifikasi
Tes HTTP LAN menggunakan loopback: token, range/suffix range, penolakan path lain, WebVTT dan penutupan server. SOAP DLNA diuji melalui server lokal dan adaptor Google Cast diuji tanpa perangkat fisik. EXE memuat modul/protokol/dependensi dan server receiver. **Chromecast, Smart TV, HP dan Miracast fisik belum diuji pada lingkungan CI**; status tidak dianggap PASS hardware.

Tools: PyChromecast (MIT), zeroconf (LGPL), UPnP AVTransport, HTTP range server Python dan panel Miracast Windows.
Referensi: https://github.com/home-assistant-libs/pychromecast
https://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf
