# SPS Beas Monitor 🚀

Projeto automatizado e de alta performance para monitoramento e reinício inteligente de serviços BEAS em ambientes SAP HANA. 

O sistema realiza validações ativas na infraestrutura, detecta serviços travados em tempo real (Heartbeat do BEAS Common), valida a comunicação do BSL (OData), monitora Portais Web e reinicia os serviços afetados caso necessário, diretamente via processos e banco de dados.

---

## 🌟 Principais Recursos e Otimizações

- **Conexão Singleton (Fail-Fast):** O script compartilha de forma inteligente uma única conexão com o banco SAP HANA. Se o banco cair, o script pula as checagens imediatamente, impedindo travamentos de 15 minutos e reduzindo a checagem geral para cerca de 1 a 2 segundos.
- **Leitura Nativa 64-bits:** Módulo de registro integrado que ignora nativamente o WOW6432Node do Windows, garantindo que os serviços do BEAS sejam identificados perfeitamente pelo Python, seja em 32-bits ou 64-bits.
- **Checagem OData (BSL):** Realiza login autenticado nas portas do BSL.
- **Restart Automático de Serviços (Taskkill):** Detecta o PID travado e realiza a derrubada forçada, reiniciando o serviço pelo Windows e alimentando a tabela `BEAS_COMMON_INPUT`.
- **Monitoramento de RAM:** Checagem e log inteligente de consumo de memória.

---

## 📂 Estrutura do Projeto

```text
SPSBeasMonitor/
├── .env.example        # Arquivo de modelo das credenciais (DB, Portas, etc)
├── app.py              # Script orquestrador de checagens (Entrypoint)
├── config.py           # Lê as credenciais do arquivo ".env"
├── database.py         # Controla o acesso ao HANA (Singleton) evitando timeouts múltiplos
├── registry.py         # Isola leitura das chaves do Regedit (bypass WOW6432Node)
├── monitors.py         # Detém a inteligência de negócios (Ping, oData, SQL Execution)
├── logger.py           # Configura os logs (cria rotações semanais/mensais nativas)
└── run_app.ps1         # Script PowerShell de gatilho para o Task Scheduler do Windows
```

---

## 🛠️ Requisitos

- Python 3.13+
- Dependências Externas (instale via pip no ambiente do servidor):
  ```cmd
  pip install ping3 hdbcli psutil requests python-dotenv
  ```
- Serviços BEAS instalados e configurados no Registro Local do Windows (Aviso: **O script requer privilégios de Administrador** para ler o status dos serviços via `psutil`).

---

## 🚀 Instalação e Configuração

1. Clone o repositório no seu servidor (Recomendado clonar diretamente em `C:\SPSBeasMonitor`):
   ```cmd
   git clone https://github.com/thierryrs1/SPSBeasMonitor.git C:\SPSBeasMonitor
   cd C:\SPSBeasMonitor
   ```

2. Configure suas variáveis de ambiente:
   - Faça uma cópia do arquivo `.env.example` e renomeie para `.env`
   - Preencha suas credenciais do banco HANA e as *flags* de ativação.

3. Agende a execução automática no Windows:
   Abra o **CMD como Administrador** e execute:
   ```cmd
   schtasks /create /sc minute /mo 1 /tn "SPSBeasMonitor" /tr "powershell.exe -ExecutionPolicy Bypass -File C:\SPSBeasMonitor\run_app.ps1" /rl HIGHEST
   ```
   *(A flag `/rl HIGHEST` garante a permissão de administrador na tarefa agendada).*

---

## 📄 Licença e Uso

Sistema desenvolvido para operação interna de monitoramento de instâncias BEAS e SAP HANA.
