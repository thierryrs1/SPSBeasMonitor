# install.ps1 - Script de Instalação Automatizada do SPSBeasMonitor

$taskName = "SPSBeasMonitor"
$appPath = "$PSScriptRoot\SPSBeasMonitor.exe"
$envFile = "$PSScriptRoot\.env"
$envExample = "$PSScriptRoot\.env.example"

Write-Host "Iniciando instalação do SPSBeasMonitor..." -ForegroundColor Cyan

# 1. Copia o .env.example para .env se não existir
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "[OK] Arquivo .env criado. (Lembre-se de editá-lo com as credenciais!)" -ForegroundColor Green
    } else {
        Write-Host "[Aviso] Arquivo .env.example não encontrado." -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] Arquivo .env já existe." -ForegroundColor Green
}

# 2. Verifica se o executável existe
if (-not (Test-Path $appPath)) {
    Write-Host "[Erro] Executável $appPath não encontrado! Faça o build do PyInstaller primeiro." -ForegroundColor Red
    exit 1
}

# 3. Cria a tarefa no Agendador do Windows (Rodando a cada 1 minuto com privilégios máximos)
Write-Host "Criando tarefa no Agendador do Windows..." -ForegroundColor Cyan

$action = New-ScheduledTaskAction -Execute $appPath -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Registra a tarefa
Register-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -TaskName $taskName -Description "Monitoramento automático dos serviços BEAS (SPS)" -Force | Out-Null

Write-Host "[OK] Tarefa '$taskName' criada com sucesso no Agendador do Windows!" -ForegroundColor Green
Write-Host "Instalação concluída! O monitor já está rodando em background a cada 1 minuto." -ForegroundColor Green
