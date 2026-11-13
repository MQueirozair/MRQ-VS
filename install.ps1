# Instalador do MRQ Audio Studio (MRQ VS) para Windows.
#
#   irm https://raw.githubusercontent.com/MQueirozair/MRQ-VS/main/install.ps1 | iex
#
# Baixa o mrq-vs.exe da última release, põe em %LOCALAPPDATA%\MRQVS,
# cria o ícone "MRQ Audio Studio" na Área de Trabalho e no Menu Iniciar,
# adiciona ao PATH do usuário e confere dependências. Sem admin.
$ErrorActionPreference = "Stop"
$repo = "MQueirozair/MRQ-VS"
$dest = Join-Path $env:LOCALAPPDATA "MRQVS"
$exe = Join-Path $dest "mrq-vs.exe"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$url = "https://github.com/$repo/releases/latest/download/mrq-vs-windows-x64.exe"
Write-Host "baixando $url"
Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dest*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$dest", "User")
  Write-Host "adicionei $dest ao PATH do usuário (reabra o terminal)"
}
$env:Path = "$env:Path;$dest"

# Cria ícone na Área de Trabalho e no Menu Iniciar
$wsh = New-Object -ComObject WScript.Shell
foreach ($pasta in @(
  [Environment]::GetFolderPath("Desktop"),
  [Environment]::GetFolderPath("Programs")
)) {
  if ($pasta -and (Test-Path $pasta)) {
    $lnk = Join-Path $pasta "MRQ Audio Studio.lnk"
    $atalho = $wsh.CreateShortcut($lnk)
    $atalho.TargetPath = $exe
    $atalho.WorkingDirectory = $dest
    $atalho.IconLocation = "$exe,0"
    $atalho.Description = "MRQ Audio Studio — Separador de Stems e Editor Musical"
    $atalho.Save()
    Write-Host "atalho criado: $lnk"
  }
}

Write-Host "`ninstalado em $exe"
& $exe doctor

@"

Próximos passos:
  Para abrir o programa: clique duas vezes no ícone "MRQ Audio Studio" na Área de Trabalho!
  ffmpeg (obrigatório p/ MP3/MP4 e áudio do YouTube)
    winget install Gyan.FFmpeg
  yt-dlp (baixar do YouTube)
    winget install yt-dlp
  separação por IA (opcional, recomendado)
    python -m pip install demucs      # ~2 GB, traz torch
"@ | Write-Host
