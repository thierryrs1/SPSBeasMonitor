# SPS Beas Monitor 🚀

Solução de alta performance, standalone e automatizada para o monitoramento e reinício inteligente de serviços BEAS em ambientes SAP HANA. 

Este sistema foi arquitetado para realizar validações ativas na infraestrutura, identificar serviços travados, matar processos duplicados ("zumbis"), checar portas OData (BSL) e portais Web e fazer o restart autônomo sem intervenção humana.

---

## 💡 Principais Funcionalidades e Inovações

- **Executável Standalone (.exe):** Agora totalmente empacotado em um único binário (SPSBeasMonitor.exe), não necessita da instalação prévia do Python, pip ou bibliotecas (como hdbcli, psutil, etc) nas máquinas dos clientes.
- **Fail-Fast com Singleton HANA:** Apenas uma conexão é compartilhada por toda a execução. Se o banco de dados cair, o monitor aborta imediatamente sem gargalos, concluindo a execução em milissegundos.
- **Smart Restart em Massa (HANA Startup):** O monitor identifica quando o servidor HANA acabou de reiniciar e aguarda 5 minutos de "aquecimento" antes de disparar um restart limpo e em massa de todos os serviços BEAS.
- **Limpeza de Múltiplos PIDs:** Rastreador de processos do Windows que detecta e finaliza múltiplos processos (beas.exe) apontando para o mesmo serviço, matando-os silenciosamente.
- **Leitura do Registro do Windows (Native):** Identifica automaticamente as senhas (html_comm) e configurações extraindo dados direto do Regedit.

---

## 📁 Estrutura do Repositório

`	ext
SPSBeasMonitor/
├── deploy/                     # 📦 PACOTE DE DISTRIBUIÇÃO (Tudo que o cliente precisa)
│   ├── .env.example            # Modelo de variáveis de ambiente
│   ├── install.ps1             # Script que instala o serviço automaticamente
│   ├── SPSBeasMonitor.exe      # Executável gerado
│   └── SPSBeasMonitor_Release_v1.0.X.zip  # Arquivo pronto pra publicar no GitHub
├── src/                        # 💻 CÓDIGO-FONTE PYTHON
│   ├── app.py                  # Entrypoint do sistema
│   ├── config.py               # Manipulação de variáveis .env e tipagem
│   ├── database.py             # Instância Singleton do SAP HANA
│   ├── logger.py               # Geração e Rotação de logs semanais
│   ├── monitors.py             # Regras de Negócio (OData, Ping, Atividades, Common)
│   └── registry.py             # Leitor de chaves do Windows
└── .gitignore                  # Arquivo para não sujar o Github com builds locais
`

---

## ⚙️ Instalação no Cliente

A instalação nunca foi tão fácil. **Você só precisa dos arquivos da pasta deploy/**.

1. Crie uma pasta no servidor do cliente (Ex: C:\SPSBeasMonitor).
2. Extraia o conteúdo do arquivo .zip da última Release nela.
3. Clique com o botão direito no arquivo **install.ps1** e selecione **Executar com o PowerShell** (Pode exigir privilégios de Administrador).

**O script de instalação fará 3 coisas:**
- Vai clonar o .env.example para .env e abrir o bloco de notas para você preencher os dados do HANA.
- Vai criar automaticamente a Tarefa no **Agendador de Tarefas do Windows**, agendada para rodar silenciosamente a cada 1 minuto com privilégios máximos.
- Vai executar o monitor pela primeira vez e criar a pasta logs/.

---

## 🛠️ Variáveis de Ambiente (.env)

O comportamento do executável é guiado pelas variáveis abaixo:
`env
DBTYPE=HANA
DB_SERVER=ip_do_hana:30015
DB_USERNAME=usuario
DB_PASSWORD=senha
DB_PORT=30015

COMMON_LIMIT_TIME=10             # Minutos para tolerar travamento no Heartbeat Common
CHECK_BSL=true                   # Liga/Desliga check de portal OData BSL
CHECK_WEB=true                   # Liga/Desliga check de portal Web Apps (Ping)
CHECK_SERVER=true                # Liga/Desliga check de Atividades do Beas (service_order=1)
CHECK_MULTIPLE_PIDS=true         # Liga/Desliga detecção de processos zumbis
`

---

## 📝 Regras de Negócio Importantes

* **Beas - Gerenciamento de Serviço:** O Monitor de "Atividades" SÓ atua nos serviços BEAS onde a chave service_order está definida como "1" no Regedit. Se for "1", o monitor garante a existência da atividade no HANA, forçando um CURRENT_TIMESTAMP inicial e reiniciando o serviço se a atividade não for executada pelo Beas a cada 2~5 minutos.
* **Beas Common:** Semelhante ao script anterior, atua verificando o Heartbeat caso service_common seja "1".
* **Portas Web e BSL:** Utilizam service_html = "1".
* O executável foi fortemente blindado utilizando **Pyright** e segue a formatação rigorosa **PEP-8**.

---
Feito com ☕ e focado em estabilidade.