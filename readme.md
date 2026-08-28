# SPS Beas Monitor

Projeto para monitoramento e reinício automático de serviços BEAS em ambiente SAP HANA.  
Permite verificar IPs e portas, checar status de serviços (BSL, Server) e atualizar tabelas de heartbeat (Common) automaticamente.

---

## Estrutura do Projeto

SPSBeasMonitor/
│
├─ .env                # Variáveis de conexão do Banco (DBTYPE, DB_SERVER, DB_USERNAME, DB_PASSWORD)
├─ app.py              # Script orquestrador de checagens (Entrypoint)
├─ config.py           # Lê as credenciais do .env via classe abstrata
├─ database.py         # Controla acesso ao HANA via ContextManager (elimina memory leaks)
├─ registry.py         # Isola leitura das chaves REGEDIT para obter IPs e Portas do Beas
├─ monitors.py         # Detém a inteligência de negócios (Ping, oData, SQL Execution)
├─ logger.py           # Configura os logs p/ criar rotações mensais/semanais nativas
├─ run_app.ps1         # Script PowerShell para executar no Windows Task Scheduler
└─ README.md           # Este arquivo


---

## Requisitos

- Python 3.13+
- Dependências Externas (instalar via pip no ambiente do servidor):
  `pip install ping3 hdbcli psutil requests python-dotenv`
- Windows PowerShell
- Permissão para executar scripts PowerShell (`ExecutionPolicy` configurado como `Bypass` se necessário)
- Serviços BEAS instalados e configurados no Registro Local do Windows

---

## Execução

### Via Agendador de tarefas

Execute via cmd como administrador:
```cmd
schtasks /create /sc minute /mo 1 /tn "SPSBeasMonitor" /tr "powershell.exe -ExecutionPolicy Bypass -File C:\SPSBeasMonitor\run_app.ps1"
```