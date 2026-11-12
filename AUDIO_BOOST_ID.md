# Audio Boost untuk video yang terlalu pelan

Volume player kini 0–200%, dengan angka persentase yang dapat diketik. Awal aplikasi memakai 100%, sebelumnya 80%. **BOOST Maks** di bar player langsung memilih volume 200%, penguatan +20 dB, EQ flat dan kompresor penahan puncak; mode normalisasi lama dinonaktifkan supaya tidak melawan penguatan.

Audio Studio menyediakan +6 dB, +12 dB, Boost Maks, pengaturan 0–20 dB, checkbox kompresor, dan Reset suara. Mulai dari +6/+12 dB bila +20 dB menghasilkan suara pecah. **Normal 100%** pada bar player atau Reset suara mengembalikan volume 100%, gain 0, menonaktifkan EQ/headroom dan mem-bypass DSP. Ini jalur suara asli pada level nominal, bukan preset EQ yang masih dapat mengurangi gain. Boost dapat bekerja saat EQ band tidak aktif. Auto-headroom EQ diperhitungkan sebelum boost; gain efektif dibatasi ±20 dB melalui filter gain terpisah.

Pengaturan profil audio tersimpan bersama preset bila penyimpanan aplikasi aktif. Saat renderer/PiP diganti, gain, volume dan status mute diterapkan kembali. Pemutar kedua tetap mengikuti mute miliknya sendiri. Boost memengaruhi pemutaran player utama, bukan otomatis membakar gain ke hasil cutting, editor atau browser. Gunakan volume klip/layer pada Video Studio untuk mengubah suara hasil ekspor.

Kompresor membantu menahan puncak tetapi bukan limiter brick-wall setelah seluruh gain/output Windows. Suara tetap bisa clipping/distorsi dan noise ikut terangkat. Nilai persentase VLC bukan jaminan kelipatan kenyaringan fisik. Periksa Volume Mixer Windows, track audio yang benar, mute dan perangkat output jika suara masih kecil; aplikasi tidak mengubah volume sistem atau amplifier speaker.

Pengujian EXE memeriksa gain native VLC, volume 200%, decoding file sintetis pelan, reset dan ketahanan mute/gain saat renderer dibuat ulang. Speaker fisik dan kenyaringan pada komputer pengguna tidak diukur di CI.

### Volume benar-benar diterapkan

Player mengulang pengaturan volume/mute selama output audio baru belum siap, setelah membuka media atau mengganti renderer. Pengulangan berhenti ketika VLC menerima pengaturan, agar tidak terus-menerus memaksa perubahan mixer. Beberapa backend audio tidak menyediakan readback volume yang akurat; sampel PCM dipakai pada pengujian untuk memastikan gain aktual. Mode Normal mem-bypass EQ dan DSP. Uji EXE menggunakan output PCM memori libVLC untuk membandingkan level RMS Normal dengan dekode sumber, memeriksa kenaikan RMS saat boost, lalu memastikan Reset kembali ke level sumber. Ini pengukuran software, bukan pengukuran speaker fisik.

EQ dan dinamika kini dimuat bersama sebagai satu rangkaian filter saat output dibuat. Ini menghindari API equalizer yang menggantikan rangkaian efek. Perubahan gain/band/dinamika dapat membuat ulang output sebentar; posisi dan pause/mute dipertahankan. Mode normal mengirim konfigurasi filter kosong secara eksplisit.

### Koreksi pelemahan equalizer

Equalizer VLC 3.x memakai faktor input 0,25. Preamp native 0 dB pada EQ flat berarti turun sekitar 12,04 dB. Cyber80 kini menetralkan faktor itu saat EQ aktif dan memakai filter gain tersendiri untuk preamp/boost pengguna. Mode Normal benar-benar bypass, dan preset Boost tidak perlu mengaktifkan EQ band. Konfigurasi per-player diterapkan pada bundel VLC 3.x 64-bit yang diuji; internal ABI VLC 4 belum didukung.
