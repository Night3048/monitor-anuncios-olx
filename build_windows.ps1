<#
  Prepara a aplicação Windows e, se Inno Setup estiver instalado, cria o
  instalador para utilizadores finais. Este script é para o PC de build; quem
  instala a aplicação não precisa de usar PowerShell nem Python.
#>
param(
  # Repositório público cujas releases a aplicação consulta ao arrancar.
  [string]$GitHubRepository = "Night3048/monitor-anuncios-olx"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Version = (Get-Content -Raw -Path (Join-Path $Root "VERSION")).Trim()

# Usa o launcher Python do Windows e isola as bibliotecas de compilação num venv.
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Instala Python 3.11 ou superior para preparar a versão de instalação." }
$Venv = Join-Path $Root ".buildenv"
$Temp = Join-Path $env:TEMP ("ProcuradorAnunciosBuild-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
$env:TEMP = $Temp
$env:TMP = $Temp
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) { py -3 -m venv $Venv }
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip --version *> $null
if ($LASTEXITCODE -ne 0) { py -3 -m venv --clear $Venv }
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "A instalação das dependências de compilação falhou." }

# A versão e o repositório ficam embutidos no executável produzido.
$RepositoryLiteral = $GitHubRepository.Replace("'", "")
$VersionLiteral = $Version.Replace("'", "")
@"
VERSION = '$VersionLiteral'
GITHUB_REPOSITORY = '$RepositoryLiteral'
"@ | Set-Content -Encoding UTF8 (Join-Path $Root "procurador\build_info.py")

# Inclui a interface e a configuração inicial dentro do executável independente.
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name ProcuradorAnuncios `
  --add-data "procurador\templates;procurador\templates" `
  --add-data "procurador\static;procurador\static" `
  --add-data "data;data" `
  main.py
if ($LASTEXITCODE -ne 0) { throw "A criação da aplicação falhou." }

# Procura o compilador do Inno Setup no PATH e nos locais comuns do Windows.
$Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($Compiler) { $CompilerPath = $Compiler.Source }
else {
  $Candidates = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
  $CompilerPath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $CompilerPath) { throw "Aplicação criada em dist\ProcuradorAnuncios.exe. Instala Inno Setup 6 e volta a executar este script para gerar o instalador." }
& $CompilerPath "/DAppVersion=$Version" "/DSourceDir=$Root\dist" (Join-Path $Root "installer\ProcuradorAnuncios.iss")
if ($LASTEXITCODE -ne 0) { throw "A criação do instalador falhou." }
Write-Host "Instalador pronto: $Root\dist\ProcuradorAnuncios-Setup.exe"
