param(
  [Parameter(Mandatory=$true)][string]$Root,
  [switch]$NoOpen
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$iconDir = Join-Path $Root 'shortcut-icons'
New-Item -ItemType Directory -Path $iconDir -Force | Out-Null
$icon = Join-Path $iconDir 'deepseek-official.ico'
$temporary = Join-Path $iconDir ('download-' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
  Invoke-WebRequest -Uri 'https://www.deepseek.com/favicon.ico' -OutFile $temporary -TimeoutSec 30
  $bytes = [IO.File]::ReadAllBytes($temporary)
  if($bytes.Length -lt 22 -or $bytes.Length -gt 2097152 -or $bytes[0] -ne 0 -or $bytes[1] -ne 0 -or $bytes[2] -ne 1 -or $bytes[3] -ne 0){throw 'Official favicon download was not a valid-sized ICO file.'}
  Move-Item -LiteralPath $temporary -Destination $icon -Force
} catch {
  if(-not(Test-Path -LiteralPath $icon)){throw 'Could not download the official DeepSeek icon. Check network and run this command again.'}
  Write-Warning 'Icon download failed; reusing the previously downloaded icon.'
} finally {
  if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary}
}
$desktop = [Environment]::GetFolderPath('Desktop')
if(-not $desktop){throw 'Windows Desktop directory could not be resolved.'}
$shortcut = Join-Path $desktop 'DeepSeek 官方 API 密钥.url'
if(Test-Path -LiteralPath $shortcut){
  $backupDir = Join-Path $Root 'backups'
  New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
  Copy-Item -LiteralPath $shortcut -Destination (Join-Path $backupDir ('deepseek-shortcut-' + [guid]::NewGuid().ToString('N') + '.url'))
}
$content = "[InternetShortcut]`r`nURL=https://platform.deepseek.com/api_keys`r`nIconFile=$icon`r`nIconIndex=0`r`n"
[IO.File]::WriteAllText($shortcut,$content,[Text.Encoding]::Unicode)
Write-Host "Desktop shortcut created: $shortcut"
Write-Host 'Sign in manually on the official website. Create keys and handle any recharge yourself.'
if(-not $NoOpen){Start-Process 'https://platform.deepseek.com/api_keys'}
