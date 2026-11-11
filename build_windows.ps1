$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not [Environment]::Is64BitProcess) { throw 'Gunakan Python/PowerShell 64-bit.' }
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Pasang Python 3.11/3.12 64-bit.' }
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Instalasi dependency gagal.' }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tes gagal.' }
$VlcDirectory = Join-Path $env:ProgramFiles 'VideoLAN\VLC'
if ($env:LINGUAPLAYER_VLC_DIR) { $VlcDirectory = $env:LINGUAPLAYER_VLC_DIR }
if (-not (Test-Path (Join-Path $VlcDirectory 'libvlc.dll'))) { throw 'Pasang VLC Windows 64-bit resmi dahulu, atau set LINGUAPLAYER_VLC_DIR.' }
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name LinguaPlayer --collect-all imageio_ffmpeg --add-data "${VlcDirectory};vlc" app.py
if ($LASTEXITCODE -ne 0) { throw 'Build gagal.' }
Copy-Item QUICK_START_ID.txt dist\LinguaPlayer\
Copy-Item LICENSE dist\LinguaPlayer\
Copy-Item README_ID.md dist\LinguaPlayer\
Copy-Item THIRD_PARTY.md dist\LinguaPlayer\
Write-Host 'Selesai: dist\LinguaPlayer\LinguaPlayer.exe. Bagikan seluruh folder, bukan EXE saja.'
