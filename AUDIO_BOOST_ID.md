# Audio Boost untuk video yang terlalu pelan

Volume player kini 0–200%, dengan angka persentase yang dapat diketik. Awal aplikasi memakai 100%, sebelumnya 80%. **BOOST Maks** di bar player langsung memilih volume 200%, preamp +20 dB, EQ flat dan kompresor penahan puncak; mode normalisasi lama dinonaktifkan supaya tidak melawan penguatan.

Audio Studio menyediakan +6 dB, +12 dB, Boost Maks, pengaturan 0–20 dB, checkbox kompresor, dan Reset suara. Mulai dari +6/+12 dB bila +20 dB menghasilkan suara pecah. Reset mengembalikan volume 100%, gain 0 dan EQ flat. Boost dapat bekerja saat EQ band tidak aktif. Auto-headroom EQ diperhitungkan sebelum boost; preamp akhir tetap dibatasi ±20 dB sesuai libVLC.

Pengaturan profil audio tersimpan bersama preset bila penyimpanan aplikasi aktif. Saat renderer/PiP diganti, gain, volume dan status mute diterapkan kembali. Pemutar kedua tetap mengikuti mute miliknya sendiri. Boost memengaruhi pemutaran player utama, bukan otomatis membakar gain ke hasil cutting, editor atau browser. Gunakan volume klip/layer pada Video Studio untuk mengubah suara hasil ekspor.

Kompresor membantu menahan puncak tetapi bukan limiter brick-wall setelah seluruh gain/output Windows. Suara tetap bisa clipping/distorsi dan noise ikut terangkat. Nilai persentase VLC bukan jaminan kelipatan kenyaringan fisik. Periksa Volume Mixer Windows, track audio yang benar, mute dan perangkat output jika suara masih kecil; aplikasi tidak mengubah volume sistem atau amplifier speaker.

Pengujian EXE memeriksa gain native VLC, volume 200%, decoding file sintetis pelan, reset dan ketahanan mute/gain saat renderer dibuat ulang. Speaker fisik dan kenyaringan pada komputer pengguna tidak diukur di CI.
