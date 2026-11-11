# AI lokal Cyber80 Players

Modul ini adalah adapter untuk layanan lokal sungguhan, bukan model yang dibundel dalam EXE. Pasang server/model hanya dari sumber resminya. Unduhan model terpisah dapat berukuran besar. Tidak ada panggilan Gemini atau key Google dalam jalur lokal.

1. Siapkan [Whisper.cpp](https://github.com/ggml-org/whisper.cpp/tree/master/examples/server) dan model multilingual, misalnya `ggml-base.bin` (bukan varian `.en` bila ingin deteksi multibahasa).
2. Jalankan `whisper-server -m lokasi-model/ggml-base.bin -l auto --host 127.0.0.1 --port 8080` sesuai binary/versi server yang dipasang.
3. Siapkan [Ollama](https://ollama.com/) dan model terjemahan yang tersedia pada perangkat. Contoh konfigurasi aplikasi menggunakan `qwen2.5:3b`; unduh melalui `ollama pull qwen2.5:3b` jika memilih model itu. Kebutuhan RAM/VRAM bergantung model dan quantization.
4. Pada Subtitle / AI pilih **AI lokal — Whisper + Ollama**. Isi URL Whisper `http://127.0.0.1:8080/inference`, URL Ollama `http://127.0.0.1:11434/api/generate`, dan nama model yang benar-benar sudah tersedia.
5. Buka media, pilih bahasa tujuan, lalu Buat/Lanjutkan. Jika server/model belum siap, aplikasi menampilkan error dan tidak beralih ke cloud.

API adapter memakai multipart WAV ke Whisper dan JSON nonstreaming ke Ollama. Keduanya dibatasi ke loopback HTTP; URL eksternal, kredensial di URL, query, proxy lingkungan dan redirect ditolak. Model dapat memberi timestamp/terjemahan yang salah; tinjau hasil. Jika STT hanya mengembalikan teks tanpa timestamp, subtitle memakai satu cue sepanjang potongan audio.
