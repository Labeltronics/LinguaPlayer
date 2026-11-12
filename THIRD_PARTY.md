# Tools dan lisensi

Kode aplikasi asli Cyber80 Players: MIT, lihat LICENSE.
Dependency tidak disertakan dalam ZIP sumber ini. Build mengunduh dependency melalui pip dan menyalin VLC yang terpasang.

- VLC / libVLC: https://www.videolan.org/vlc/ dan https://code.videolan.org/videolan/vlc — komponen VLC umumnya GPL/LGPL; lihat COPYING dan lisensi setiap plugin pada distribusi yang dibundel.
- python-vlc: https://github.com/oaubert/python-vlc — LGPL-2.1.
- PySide6 / Qt for Python: https://code.qt.io/cgit/pyside/pyside-setup.git/ — LGPL-3.0/GPL atau komersial; gunakan dynamic libraries, sertakan pemberitahuan/lisensi dan hak penggantian library saat mendistribusikan.
- imageio-ffmpeg: https://github.com/imageio/imageio-ffmpeg — BSD-2-Clause untuk wrapper. FFmpeg binary memiliki lisensi sendiri sesuai build, LGPL/GPL. Lihat https://ffmpeg.org/legal.html.
- PyInstaller: https://github.com/pyinstaller/pyinstaller — GPL dengan pengecualian untuk bundling aplikasi.

Sebelum distribusi publik, pertahankan seluruh file lisensi dependency dan sediakan source/penawaran source yang diwajibkan oleh lisensi build VLC/FFmpeg/Qt yang dipilih. ZIP ini bukan sertifikasi kepatuhan lisensi atau paket codec universal.

- NumPy: https://github.com/numpy/numpy — BSD-3-Clause dan lisensi komponen bawaan; lisensi di metadata distribusi yang dibundel.
- Adapter layanan lokal mengikuti API Whisper.cpp (https://github.com/ggml-org/whisper.cpp) dan Ollama (https://github.com/ollama/ollama); server/model tidak dibundel dan mempunyai lisensi masing-masing.

## Browser dan stereo depth
Qt WebEngine/Chromium mengikuti lisensi Qt dan komponen Chromium dari distribusi PySide6; codec web tidak identik dengan VLC. ONNX Runtime/DirectML mengikuti lisensi distribusinya. MiDaS v2.1 small memakai MIT; lisensi, URL sumber dan checksum model disertakan di models/. Model asli: https://github.com/isl-org/MiDaS . Runtime: https://onnxruntime.ai/ . Tidak ada bobot model berbayar atau API key yang disertakan.


Optional Voice Tools: OpenVoice (MyShell), MIT, source https://github.com/myshell-ai/OpenVoice, pinned commit 74a1d147b17a8c3092dd5430504bd83ef6c7eb23. Installer obtains official V2 converter separately and copies its LICENSE. Separate portable Python (PSF), PyTorch/Torchaudio (BSD), NumPy (BSD), librosa (ISC), SoundFile (BSD) and their dependencies retain package license metadata. No OpenVoice code/model or PyTorch is embedded in the main EXE.
