# Monta a pasta/zip para levar à TV box por pendrive.
# Uso (na raiz do projeto): powershell -File deploy\gerar_pacote.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$saida = Join-Path $raiz "pacote_tvbox"
$zip = Join-Path $raiz "pacote_tvbox.zip"

if (Test-Path $saida) { Remove-Item -Recurse -Force $saida }
if (Test-Path $zip) { Remove-Item -Force $zip }
New-Item -ItemType Directory -Path (Join-Path $saida "deploy") | Out-Null

New-Item -ItemType Directory -Path (Join-Path $saida "src") | Out-Null
Copy-Item (Join-Path $raiz "src\*.py") (Join-Path $saida "src")
Copy-Item (Join-Path $raiz "requirements.txt") $saida
Copy-Item (Join-Path $PSScriptRoot "*") (Join-Path $saida "deploy") -Exclude "gerar_pacote.ps1"

# Scripts e unit do Linux precisam de quebra de linha LF (CRLF quebra o bash/systemd)
foreach ($arq in Get-ChildItem (Join-Path $saida "deploy") -Include *.sh, *.service -File) {
    $texto = [System.IO.File]::ReadAllText($arq.FullName) -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($arq.FullName, $texto, (New-Object System.Text.UTF8Encoding($false)))
}

Compress-Archive -Path (Join-Path $saida "*") -DestinationPath $zip
Write-Host "Pacote gerado: $zip"
Write-Host "Copie a pasta '$saida' (ou o zip) para o pendrive."
