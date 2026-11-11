# Pengujian Cyber80 Players

Tes lokal mencakup penanganan timeout/quota, penyamaran key, overlap subtitle, resume termasuk segmen hening, penyimpanan cache/riwayat, dua controller, kontrol seek/speed, profil EQ, RGB anaglyph, dan pelanjutan setelah gagal. Test adapter lokal melakukan HTTP sungguhan ke server loopback tiruan; tidak memanggil Gemini atau model lokal sesungguhnya.

Workflow Windows menjalankan tes kode, membangun EXE, menonaktifkan VLC sistem, lalu menjalankan tes penerimaan pada delapan format video dan beberapa format audio, EQ native, PiP/3D, dua video bersamaan, fullscreen, seek/speed, playlist, A-B repeat, snapshot, ketajaman dan ekspor CPU 720p/1080p/2160p. Detail hasil akhir ada pada HASIL_UJI_WINDOWS.json dalam paket build.

PASS berlaku pada sampel/skenario yang diuji. GPU fisik, HDR/monitor, kualitas akustik keluaran speaker, film panjang, dan akurasi model AI tidak dibuktikan oleh tes CI tersebut.
