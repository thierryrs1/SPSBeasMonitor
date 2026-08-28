# Obtém o diretório onde este arquivo .ps1 está salvo e navega para ele
$workingDir = $PSScriptRoot
Set-Location $workingDir

# Executa o script Python diretamente usando o Python global do sistema
python app.py