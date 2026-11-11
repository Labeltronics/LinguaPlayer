$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not [Environment]::Is64BitProcess) { throw 'Gunakan Python/PowerShell 64-bit.' }
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Pasang Python 3.11/3.12 64-bit.' }
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Instalasi dependency gagal.' }
& $Python make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Pembuatan ikon gagal.' }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tes gagal.' }
$VlcDirectory = Join-Path $env:ProgramFiles 'VideoLAN\VLC'
if ($env:LINGUAPLAYER_VLC_DIR) { $VlcDirectory = $env:LINGUAPLAYER_VLC_DIR }
if (-not (Test-Path (Join-Path $VlcDirectory 'libvlc.dll'))) { throw 'Pasang VLC Windows 64-bit resmi dahulu, atau set LINGUAPLAYER_VLC_DIR.' }
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name Cyber80Players --icon assets/cyber80.ico --add-data "assets;assets" --collect-all imageio_ffmpeg --add-data "${VlcDirectory};vlc" app.py
if ($LASTEXITCODE -ne 0) { throw 'Build gagal.' }
Copy-Item QUICK_START_ID.txt dist\Cyber80Players\
Copy-Item AUDIT_CYBER80_PLAYERS_ID.md dist\Cyber80Players\
Copy-Item PEMBARUAN_CYBER80_ID.md dist\Cyber80Players\
Copy-Item AI_LOKAL_ID.md dist\Cyber80Players\
Copy-Item LICENSE dist\Cyber80Players\
Copy-Item README_ID.md dist\Cyber80Players\
Copy-Item THIRD_PARTY.md dist\Cyber80Players\
Write-Host 'Selesai: dist\Cyber80Players\Cyber80Players.exe. Bagikan seluruh folder, bukan EXE saja.'

$PluginRoot = Join-Path $PSScriptRoot 'dist\Cyber80Players\_internal\vlc\plugins'
$Plugins = Get-ChildItem $PluginRoot -Recurse -Filter *.dll
if ($Plugins.Count -lt 100) { throw 'Plugin VLC tidak lengkap.' }
$Plugins | ForEach-Object { $_.FullName.Substring($PluginRoot.Length + 1) } | Sort-Object | Set-Content dist\Cyber80Players\CODEC_PLUGINS.txt
Write-Host "Bundled VLC plugin DLLs: $($Plugins.Count)"
