$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not [Environment]::Is64BitProcess) { throw 'Gunakan Python/PowerShell 64-bit.' }
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Pasang Python 3.11/3.12 64-bit.' }
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Instalasi dependency gagal.' }
New-Item -ItemType Directory -Force models | Out-Null
$Model = Join-Path $PSScriptRoot 'models\midas-small.onnx'
if (-not (Test-Path $Model)) { Invoke-WebRequest -Uri 'https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx' -OutFile $Model }
$ModelHash = (Get-FileHash $Model -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ModelHash -ne '2d8c6cb8f415229daf1eb041024208e2608c9f98e17c81cc7c6ecb449c56fd58') { throw 'Checksum model kedalaman tidak cocok.' }
$DnsPlan = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\cloudflare_dns.ps1 -Mode Plan
if ($LASTEXITCODE -ne 0) { throw 'DNS helper plan gagal.' }
$DnsPlanObject = $DnsPlan | ConvertFrom-Json
if ($DnsPlanObject.writes_dns -or $DnsPlanObject.servers[0] -ne '1.1.1.1') { throw 'DNS helper plan tidak sah.' }
& $Python make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Pembuatan ikon gagal.' }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tes gagal.' }
& $Python verify_audio_source.py
if ($LASTEXITCODE -ne 0) { throw 'Verifikasi level audio native gagal.' }
$VlcDirectory = Join-Path $env:ProgramFiles 'VideoLAN\VLC'
if ($env:LINGUAPLAYER_VLC_DIR) { $VlcDirectory = $env:LINGUAPLAYER_VLC_DIR }
if (-not (Test-Path (Join-Path $VlcDirectory 'libvlc.dll'))) { throw 'Pasang VLC Windows 64-bit resmi dahulu, atau set LINGUAPLAYER_VLC_DIR.' }
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name Cyber80Players --icon assets/cyber80.ico --add-data "assets;assets" --add-data "cloudflare_dns.ps1;." --collect-all imageio_ffmpeg --collect-all onnxruntime --collect-all langdetect --add-data "models;models" --add-data "${VlcDirectory};vlc" app.py
if ($LASTEXITCODE -ne 0) { throw 'Build gagal.' }
& $Python optimize_bundle.py
if ($LASTEXITCODE -ne 0) { throw 'Optimasi paket gagal.' }
& $Python bundle_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Penyalinan lisensi gagal.' }
Copy-Item QUICK_START_ID.txt dist\Cyber80Players\
Copy-Item AUDIT_CYBER80_PLAYERS_ID.md dist\Cyber80Players\
Copy-Item PEMBARUAN_CYBER80_ID.md dist\Cyber80Players\
Copy-Item CYBER80_BROWSER_3D_ID.md dist\Cyber80Players\
Copy-Item VIDEO_STUDIO_ID.md dist\Cyber80Players\
Copy-Item AUDIO_BOOST_ID.md dist\Cyber80Players\
Copy-Item PROMPT_VIDEO_STUDIO_ID.md dist\Cyber80Players\
Copy-Item GEMINI_LIVE_TEST_REPORT.json dist\Cyber80Players\
Copy-Item examples dist\Cyber80Players\ -Recurse
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
