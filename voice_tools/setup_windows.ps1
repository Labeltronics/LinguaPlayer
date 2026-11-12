param([string]$Destination = (Join-Path $env:LOCALAPPDATA 'Cyber80 Players\VoiceTools'))
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force $Destination | Out-Null
$Destination = (Resolve-Path $Destination).Path
$Python=Join-Path $Destination 'python\python.exe'
function Run-Checked([string[]]$Arguments) { & $Python @Arguments; if ($LASTEXITCODE -ne 0) { throw "Instalasi gagal: $($Arguments[0])" } }
if (-not (Test-Path $Python)) {
  Write-Host 'Mengunduh runtime Python portable 3.11.9 dari python.org ...'
  $Zip=Join-Path $Destination 'python.zip'
  Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile $Zip
  Expand-Archive -LiteralPath $Zip -DestinationPath (Join-Path $Destination 'python') -Force
  Remove-Item $Zip
  @('python311.zip','.','Lib\site-packages','import site') | Set-Content (Join-Path $Destination 'python\python311._pth') -Encoding ASCII
}
$Pip=Join-Path $Destination 'get-pip.py'
if (-not (Test-Path (Join-Path $Destination 'python\Lib\site-packages\pip'))) {
  Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile $Pip
  Run-Checked -Arguments @($Pip);Remove-Item $Pip
}
Write-Host 'Memasang PyTorch CPU dan dependencies lokal. Unduhan dapat melebihi 1 GB; tidak ada biaya API.'
Run-Checked -Arguments @('-m','pip','install','torch==2.5.1','torchaudio==2.5.1','--index-url','https://download.pytorch.org/whl/cpu')
Run-Checked -Arguments @('-m','pip','install','numpy==1.26.4','librosa==0.10.2.post1','soundfile==0.12.1','eng_to_ipa==0.0.2','inflect==7.0.0','Unidecode==1.3.7','pypinyin==0.50.0','cn2an==0.5.22','jieba==0.42.1')
$Commit='74a1d147b17a8c3092dd5430504bd83ef6c7eb23'
$CodeZip=Join-Path $Destination 'openvoice.zip'
Invoke-WebRequest "https://github.com/myshell-ai/OpenVoice/archive/$Commit.zip" -OutFile $CodeZip
$Code=Join-Path $Destination 'source'
New-Item -ItemType Directory -Force $Code | Out-Null
Expand-Archive -LiteralPath $CodeZip -DestinationPath $Code -Force
$Repo=Join-Path $Code "OpenVoice-$Commit"
Run-Checked -Arguments @('-m','pip','install','--no-deps',$Repo)
Remove-Item $CodeZip
$ModelRevision='f36e7edfe1684461a8343844af60babc2efbb727'
$Model=Join-Path $Destination 'model';New-Item -ItemType Directory -Force $Model | Out-Null
Write-Host 'Mengunduh converter V2 resmi MyShell (revision tetap, SHA256 diverifikasi) ...'
Invoke-WebRequest "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/$ModelRevision/converter/config.json" -OutFile (Join-Path $Model 'config.json')
Invoke-WebRequest "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/$ModelRevision/converter/checkpoint.pth" -OutFile (Join-Path $Model 'checkpoint.pth')
$Expected='9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e'
if ((Get-FileHash (Join-Path $Model 'checkpoint.pth') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) { throw 'Checksum model OpenVoice tidak cocok.' }
Copy-Item (Join-Path $Repo 'LICENSE') (Join-Path $Destination 'LICENSE_OpenVoice.txt') -Force
Copy-Item (Join-Path $PSScriptRoot 'worker.py') (Join-Path $Destination 'worker.py') -Force
Run-Checked -Arguments @('-c','from openvoice.api import ToneColorConverter; import torch,librosa,soundfile; print("Dependencies OK")')
@{source_commit=$Commit;model_sha256=(Get-FileHash (Join-Path $Model 'checkpoint.pth') -Algorithm SHA256).Hash;runtime='Python 3.11.9 / Torch 2.5.1 CPU';network_after_setup=$false} | ConvertTo-Json | Set-Content (Join-Path $Destination 'installation.json') -Encoding UTF8

Write-Host "Selesai. Folder Voice Tools: $Destination"
