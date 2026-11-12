param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$c = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voices = @($s.GetInstalledVoices() | Where-Object { $_.Enabled })
  $selected = $voices | Where-Object { $_.VoiceInfo.Name -eq $c.voice -and $c.voice } | Select-Object -First 1
  if (-not $selected) { $selected = $voices | Where-Object { $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq ($c.language -split '-')[0] } | Select-Object -First 1 }
  if (-not $selected) { throw 'Suara Windows untuk bahasa ini belum terpasang. Pasang suara kompatibel SAPI atau pilih Gemini TTS.' }
  $s.SelectVoice($selected.VoiceInfo.Name)
  $s.SetOutputToWaveFile($c.output)
  $s.Speak([string]$c.text)
} finally { $s.Dispose() }
