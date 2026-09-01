import os
import subprocess
import socket
import psutil
import requests
from ping3 import ping
from logger import logger
from database import db_client
from registry import BeasService
from config import config

class HanaSystemMonitor:
    """Monitor Global do Servidor HANA para eventos críticos sistêmicos."""
    
    STATE_FILE = "state_last_restart.txt"

    @staticmethod
    def check_startup_and_restart(beas_services: list[BeasService]):
        """Verifica o Start Time do servidor e reinicia todos os BEAS em massa se vida útil >= 5 minutos."""
        try:
            with db_client.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        TO_VARCHAR(START_TIME, 'YYYY-MM-DD HH24:MI:SS') AS StartTime,
                        TO_INT(SECONDS_BETWEEN(START_TIME, CURRENT_TIMESTAMP) / 60) AS DiffMinutes
                    FROM 
                        SYS.M_SERVICE_STATISTICS
                    WHERE
                        SERVICE_NAME = 'indexserver'
                    ORDER BY 
                        START_TIME DESC
                    LIMIT 1;
                """)
                row = cursor.fetchone()
                
                if not row:
                    logger.warning("[HANA Global] Não foi possível obter o START_TIME em SYS.M_SERVICE_STATISTICS.")
                    return
                    
                start_time_str = row[0]
                diff_minutes = row[1]
                
                # Levanta o status do último restart efetuado
                last_recorded = ""
                if os.path.exists(HanaSystemMonitor.STATE_FILE):
                    with open(HanaSystemMonitor.STATE_FILE, "r", encoding="utf-8") as f:
                        last_recorded = f.read().strip()
                
                # Regra: se > 5 minutos de vida, e a chave é inédita (nunca processada)
                if diff_minutes >= 5:
                    if last_recorded != start_time_str:
                        logger.warning(f"[HANA Global] HANA rodando há {diff_minutes} minutos (Startup: {start_time_str}). Iniciando restart em MASSA nos serviços BEAS...")
                        
                        for svc in beas_services:
                            SystemMonitor.restart_service(svc.service_name)
                        
                        # Trava o estado para evitar loop nos próximos 1 minutos
                        with open(HanaSystemMonitor.STATE_FILE, "w", encoding="utf-8") as f:
                            f.write(start_time_str)
                            
                        logger.info(f"[HANA Global] Restart em MASSA efetuado com sucesso! Arquivo estado travado em {start_time_str}.")
                    else:
                        logger.debug(f"[HANA Global] Restart massivo do último ligamento já foi executado ({last_recorded}). Ignorando novos comandos.")
                else:
                    logger.info(f"[HANA Global] HANA subiu há apenas {diff_minutes} minutos. Aguardando amadurecer a marca de 5 minutos...")

        except Exception as e:
            logger.error(f"[HANA Global] Falha crítica ao auditar a SYS.M_SERVICE_STATISTICS: {e}")

class SystemMonitor:
    """Monitor de infraestrutura de Sistema Operacional e conectividade."""
    
    @staticmethod
    def monitor_ram(threshold=85):
        try:
            uso_ram = psutil.virtual_memory().percent
            logger.info(f"[Sistema] [Monitor RAM] Uso atual de RAM: {uso_ram:.2f}%")
            if uso_ram >= threshold:
                logger.warning(f"[Sistema] [Monitor RAM] ⚠️ Alerta: Uso de RAM acima de {threshold}% ({uso_ram:.2f}%)")
        except Exception as e:
            logger.error(f"[Sistema] [Monitor RAM] ❌ Erro ao monitorar RAM: {e}")

    @staticmethod
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_local = s.getsockname()[0]
            s.close()
            return ip_local
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def kill_port(port: int):
        killed = []
        for conn in psutil.net_connections():
            if conn.laddr and conn.laddr.port == port:
                pid = conn.pid
                if pid:
                    try:
                        p = psutil.Process(pid)
                        p.kill()
                        killed.append(pid)
                    except Exception as e:
                        logger.error(f"[Sistema] Erro ao matar PID {pid} na porta {port}: {e}")
        
        if killed:
            logger.info(f"[Sistema] Processos finalizados na porta {port}: {killed}")
        else:
            logger.info(f"[Sistema] Nenhum processo encontrado aberto na porta {port}")

    @staticmethod
    def check_multiple_pids(service_name: str) -> bool:
        """
        Verifica para cada beasService se existe mais de um PID no Windows.
        Se tiver mais de um PID, usa taskkill em todos os PIDs e depois inicia o serviço novamente.
        Retorna True se realizou as ações, False caso contrário.
        """
        try:
            service = psutil.win_service_get(service_name)
            binpath = service.binpath()
            if not binpath:
                return False
                
            exe_path = ""
            if ".exe" in binpath.lower():
                idx = binpath.lower().find(".exe") + 4
                exe_path = binpath[:idx].strip('"\' ')
                
            if not exe_path:
                return False

            matching_processes = {}
            binpath_clean = binpath.replace('"', '').replace("'", "").strip().lower()

            for p in psutil.process_iter(['pid', 'exe', 'cmdline']):
                try:
                    p_exe = p.info.get('exe')
                    p_cmdline = p.info.get('cmdline')
                    
                    if not p_exe or not p_cmdline:
                        continue
                        
                    cmd_str = " ".join(p_cmdline)
                    cmd_str_clean = cmd_str.replace('"', '').replace("'", "").strip().lower()
                    
                    # Regra para associar o processo a este serviço de forma EXATA
                    # 1. O nome do serviço é uma correspondência exata em algum parâmetro da linha de comando
                    # 2. A linha de comando limpa é idêntica ao binpath limpo
                    # 3. Ambos (cmdline e binpath) são estritamente apenas o executável
                    
                    is_exact_match = False
                    target_svc = service_name.lower()
                    
                    for arg in p_cmdline:
                        arg_lower = arg.lower()
                        if arg_lower == target_svc:
                            is_exact_match = True
                            break
                        # Trata casos como -service=beasService_1 ou servermodus=beasService10
                        if '=' in arg_lower:
                            if target_svc in arg_lower.split('='):
                                is_exact_match = True
                                break
                        # Trata casos como -service:beasService_1
                        if ':' in arg_lower and len(arg_lower) > 2 and not arg_lower[1] == ':': # ignorando C:\
                            if target_svc in arg_lower.split(':'):
                                is_exact_match = True
                                break

                    # Match pelo binpath também
                    matched = False
                    if is_exact_match:
                        matched = True
                    elif p_exe.lower() == exe_path.lower() and cmd_str_clean == binpath_clean:
                        matched = True
                    elif p_exe.lower() == exe_path.lower() and cmd_str_clean == exe_path.lower() and binpath_clean == exe_path.lower():
                        matched = True
                        
                    if matched:
                        exe_name = p_exe.split('\\')[-1].lower() if p_exe else "unknown.exe"
                        matching_processes[p.info['pid']] = exe_name
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Verifica se há executáveis duplicados (focado estritamente no beas.exe conforme solicitado)
            from collections import Counter
            exe_counts = Counter(matching_processes.values())
            
            has_duplicates = exe_counts.get('beas.exe', 0) > 1
            
            if has_duplicates:
                pids_to_kill = list(matching_processes.keys())
                logger.warning(f"[{service_name}] [Monitor] ⚠️ Foram detectados processos duplicados para o serviço: {dict(exe_counts)}")
                for pid in pids_to_kill:
                    logger.warning(f"[{service_name}] [Monitor] 🗡️ Forçando finalização no PID {pid} via taskkill...")
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Garante o stop via sc apenas por desencargo
                subprocess.run(["sc", "stop", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                logger.info(f"[{service_name}] [SC] ▶️ Iniciando serviço novamente: {service_name}")
                subprocess.run(["sc", "start", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
                
        except Exception as e:
            logger.error(f"[{service_name}] [Monitor] ❌ Erro ao validar múltiplos PIDs: {e}")
            
        return False

    @staticmethod
    def restart_service(service_name: str):
        logger.warning(f"[{service_name}] [Monitor] 🔄 Reiniciando serviço do Windows: {service_name}")
        
        try:
            service = psutil.win_service_get(service_name)
            pid = service.pid()
            
            if pid and pid > 0:
                logger.warning(f"[{service_name}] [Monitor] 🗡️ Forçando finalização no PID {pid} via taskkill...")
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                logger.info(f"[{service_name}] [Monitor] ℹ️ Serviço não possuía PID ativo (já parado).")
                
            # Garante o STOP via SC apenas por desencargo de consciência
            subprocess.run(["sc", "stop", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.error(f"[{service_name}] [Monitor] ❌ Erro ao obter PID para TASKKILL: {e}")

        logger.info(f"[{service_name}] [SC] ▶️ Iniciando serviço: {service_name}")
        subprocess.run(["sc", "start", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def disable_service(service_name: str):
        logger.warning(f"[{service_name}] [SC] 🛑 Desativando o serviço do Windows permanentemente: {service_name}")
        
        try:
            service = psutil.win_service_get(service_name)
            pid = service.pid()
            if pid and pid > 0:
                logger.warning(f"[{service_name}] [Monitor] 🗡️ Matando PID {pid} via taskkill antes de desativar...")
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        subprocess.run(["sc", "stop", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sc", "config", service_name, "start=", "disabled"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class BeasMonitor:
    """Classes de Monitoramento dedicadas às regras de negócio e estabilidade BEAS."""
    
    def __init__(self):
        self.local_ip = SystemMonitor.get_local_ip()

    def check_web_portal(self, svc: BeasService):
        """Verifica a integridade do Web Portal testando o Ping e a Porta Socket do Host."""
        if not svc.html_indexname or svc.service_html != "1":
            return
            
        port = svc.html_indexname
        schema = svc.mssql_database
        service = svc.service_name
        
        alive = False
        try:
            if ping(self.local_ip, timeout=2) is not None:
                with socket.create_connection((self.local_ip, port), timeout=2):
                    alive = True
        except Exception:
            alive = False

        if not alive:
            logger.error(f"[{service}] [Portal Web] ❌ {self.local_ip}:{port} fora do ar! Reiniciando em {schema}...")
            SystemMonitor.restart_service(service)
        else:
            logger.info(f"[{service}] [Portal Web] ✅ {self.local_ip}:{port} comunicando perfeitamente em {schema}")

    def check_bsl_odata(self, svc: BeasService):
        """Verifica se a URL odata4/Login responde ok autenticando via POST Requests."""
        if not svc.html_indexname or svc.service_html != "1":
            return
            
        port = svc.html_indexname
        schema = svc.mssql_database
        service = svc.service_name
        
        if not svc.html_comm:
            logger.error(f"[{service}] [BSL] ❌ html_comm (senha ServiceLayer) não configurado no registry em {schema}.")
            return
            
        ok = False
        message = ""
        try:
            url = f"http://{self.local_ip}:{port}/odata4/Login"
            payload = {"ServicePwd": svc.html_comm}
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                ok, message = True, "Login OK (HTTP 200)"
            else:
                ok, message = False, f"HTTP {response.status_code} - {response.text}"
        except requests.exceptions.ConnectTimeout:
            ok, message = False, "Timeout ao conectar"
        except requests.exceptions.ConnectionError:
            ok, message = False, "Falha na conexão"
        except Exception as e:
            ok, message = False, f"Erro inesperado: {e}"

        if not ok:
            logger.warning(f"[{service}] [BSL] ❌ OData BSL falhou ({message}). Matando processos e Reiniciando {service} em {schema}...")
            SystemMonitor.kill_port(port)
            SystemMonitor.restart_service(service)
        else:
            logger.info(f"[{service}] [BSL] ✅ OData Login BSL bem-sucedido em {schema}.")

    def check_system_server(self, svc: BeasService):
        """Monitora as atividades avaliando a tabela BEAS_SYS_SERVER no HANA."""
        if svc.service_order != "1":
            return
        
        schema = svc.mssql_database
        service = svc.service_name
        
        if not schema:
            logger.error(f"[{service}] [Atividades] Nenhum schema definido (mssql_database vazio).")
            return
            
        try:
            with db_client.get_connection() as conn:
                cursor = conn.cursor()
                
                # Verifica se o schema realmente existe na base antes de apontar
                cursor.execute(f"SELECT COUNT(1) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = '{schema}'")
                if cursor.fetchone()[0] == 0:
                    logger.error(f"[{service}] [Atividades] Banco de Dados '{schema}' inexistente no HANA. Desativando o serviço...")
                    SystemMonitor.disable_service(service)
                    return
                    
                cursor.execute(f"SET SCHEMA {schema};")
                cursor.execute("""
                    SELECT COUNT(1)
                    FROM "BEAS_SYS_SERVER"
                    WHERE "BEZEICHNUNG" = 'BEAS - Gerenciamento de Serviço';
                """)
                valida = cursor.fetchone()[0]
                
                if valida == 0:
                    logger.warning(f"[{service}] [Atividades] Tabela BEAS_SYS_SERVER não possui registro para 'BEAS - Gerenciamento de Serviço' em {schema}. Inserindo registro padrão...")
                    cursor.execute("""
                        INSERT INTO "BEAS_SYS_SERVER"
                        SELECT
                            (SELECT IFNULL(MAX("NR"), 0) + 1 FROM "BEAS_SYS_SERVER") AS "NR",
                            'BEAS - Gerenciamento de Serviço' AS "BEZEICHNUNG",
                            NULL AS "DESCRIPTIONID",
                            1 AS "AKTIV",
                            'XXXXXXX' AS "WOCHENTAG",
                            0 AS "UHRZEIT",
                            86340 AS "BISUHRZEIT",
                            1 AS "WIEDERHOLUNG",
                            60 AS "WIEDERHOLUNGUNIT",
                            NULL AS "EMPFAENGER",
                            'S' AS "TYPID",
                            NULL AS "PARAMETER1",
                            NULL AS "PARAMETER2",
                            NULL AS "EVENTSCRIPT",
                            NULL AS "EVENTBITMAP",
                            1 AS "SENDAS",
                            'BEAS - Gerenciamento de Serviço' AS "Subject",
                            NULL AS "LONGTEXT",
                            NULL AS "KEY1NAME",
                            0 AS "KEY1SETCLOSE",
                            NULL AS "KEY1SCRIPT",
                            NULL AS "KEY2NAME",
                            0 AS "KEY2SETCLOSE",
                            NULL AS "KEY2SCRIPT",
                            'Close' AS "KEY3NAME",
                            1 AS "KEY3SETCLOSE",
                            NULL AS "KEY3SCRIPT",
                            NULL AS "SENDUSER1",
                            NULL AS "SENDUSER2",
                            NULL AS "SENDUSER3",
                            NULL AS "BaseType",
                            NULL AS "BASENR1",
                            NULL AS "BASENR2",
                            NULL AS "BASENR3",
                            'message=info$ok' AS "AUSFUEHRUNG",
                            1 AS "MAKRO_ID",
                            NULL AS "ImportDirectory",
                            NULL AS "ImportBackupDirectory",
                            NULL AS "ImportDeleteFile",
                            NULL AS "ImportDef1",
                            NULL AS "ImportDef2",
                            NULL AS "ImportDef3",
                            NULL AS "ImportDef4",
                            NULL AS "ImportDef5",
                            NULL AS "ImportDef6",
                            NULL AS "ImportScript",
                            '*.*' AS "ImportFileMask",
                            CURRENT_TIMESTAMP AS "LETZTE_AUSFUEHRUNG",
                            NULL AS "LETZTE_MELDUNG",
                            0 AS "STATISTIC_COUNT",
                            0 AS "STATISTIC_TIMETOTAL",
                            NULL AS "STATISTIC_LASTSTART",
                            NULL AS "STATISTIC_LASTEND",
                            0 AS "STATISTIC_LASTTIME",
                            'S' AS "DOCUMENTFORMAT",
                            NULL AS "DOCUMENTNAME",
                            NULL AS "DOCUMENTVARIABLES",
                            CURRENT_TIMESTAMP AS "ERFTSTAMP",
                            'dba' AS "ERFUSER",
                            CURRENT_TIMESTAMP AS "ANDTSTAMP",
                            'dba' AS "ANDUSER"
                        FROM DUMMY;
                    """)
                    conn.commit()
                    logger.info(f"[{service}] [Atividades] Registro inserido com sucesso em {schema}.")
                    
                # Realiza a validação normal de tempo agora que garantimos que o registro existe
                cursor.execute("""
                    SELECT TO_INT(SECONDS_BETWEEN("STATISTIC_LASTSTART", CURRENT_TIMESTAMP) / 60) AS DIF_MINUTOS 
                    FROM "BEAS_SYS_SERVER"
                    WHERE "BEZEICHNUNG" = 'BEAS - Gerenciamento de Serviço';
                """)
                
                # Trata possibilidade remota do select falhar mesmo após o insert
                row = cursor.fetchone()
                if row and row[0] is not None:
                    diff = row[0]
                    if diff >= 2:
                        logger.warning(f"[{service}] [Atividades] Última execução >= 2 min ({diff} min). Reiniciando {service} em {schema}...")
                        SystemMonitor.restart_service(service)
                    else:
                        if diff < 0:
                            diff = 0
                        logger.info(f"[{service}] [Atividades] Última execução validada há {diff} min em {schema}")
        except Exception as e:
            logger.error(f"[{service}] [Atividades] Erro ao validar BEAS_SYS_SERVER: {e} em {schema}")

    def check_common_heartbeat(self, svc: BeasService, limit):
        """Valida o Heartbeat de Scripts Commons injetando uma Procedure HANA diretamente."""
        if svc.service_common != "1":
            return
            
        schema = svc.mssql_database
        service = svc.service_name
        limit = int(config.COMMON_LIMIT_TIME)

        if not schema:
            logger.error(f"[{service}] [Beas Common] Nenhum schema definido (mssql_database vazio).")
            return
            
        try:
            with db_client.get_connection() as conn:
                cursor = conn.cursor()
                
                # Verifica se o schema realmente existe na base antes de interagir
                cursor.execute(f"SELECT COUNT(1) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = '{schema}'")
                if cursor.fetchone()[0] == 0:
                    logger.error(f"[{service}] [Beas Common] Banco de Dados '{schema}' inexistente no HANA. Desativando o serviço...")
                    SystemMonitor.disable_service(service)
                    return
                
                # Check tables
                cursor.execute(f"SELECT COUNT(1) FROM \"SYS\".\"TABLES\" WHERE \"SCHEMA_NAME\" = '{schema}' AND \"TABLE_NAME\" = 'SPS_BEAS_COMMON_HEARTBEAT'")
                cnt = cursor.fetchone()[0]
                
                cursor.execute(f"SELECT COUNT(1) FROM \"SYS\".\"PROCEDURES\" WHERE \"SCHEMA_NAME\" = '{schema}' AND \"PROCEDURE_NAME\" = 'SP_SPS_BEAS_COMMON_VALIDATION'")
                cnt2 = cursor.fetchone()[0]
                
                cursor.execute(f"SET SCHEMA {schema};")
                
                if cnt2 == 0:
                    cursor.execute("""
                        CREATE PROCEDURE SP_SPS_BEAS_COMMON_VALIDATION()
                        AS BEGIN
                            DECLARE cnt INT;
                            DECLARE maxcnt INT;
                            SELECT SECONDS_BETWEEN(IFNULL(MAX("TimeLife"), ADD_SECONDS(CURRENT_TIMESTAMP, -180)), CURRENT_TIMESTAMP)
                            INTO maxcnt FROM "BEAS_COMMON_INPUT" WHERE "PARAMETER5" = 'SPS Common Check';
                            SELECT COALESCE(MAX("COUNTID")+1,1) INTO cnt FROM "BEAS_COMMON_INPUT";
                            
                            IF :maxcnt > 60 THEN
                                INSERT INTO "BEAS_COMMON_INPUT" ("COUNTID", "COMMONTYP", "PARAMETER5", "TEXTPARAMETER", "TimeLife", "ENTRYDATE") 
                                VALUES (:cnt, 'script', 'SPS Common Check', 'sqlexecute=update sps_beas_common_heartbeat set "LastUpdate" = current_timestamp where id = 1', CURRENT_TIMESTAMP, ADD_DAYS(CURRENT_TIMESTAMP,14));	
                            END IF;
                        END;
                    """)
                    
                if cnt == 0:
                    cursor.execute('CREATE TABLE "SPS_BEAS_COMMON_HEARTBEAT" ("ID" INT, "LastUpdate" TIMESTAMP);')
                    cursor.execute('INSERT INTO "SPS_BEAS_COMMON_HEARTBEAT" ("ID", "LastUpdate") VALUES (1, CURRENT_TIMESTAMP);')
                    conn.commit()
                    logger.warning(f"[{service}] [Beas Common] Tabela SPS_BEAS_COMMON_HEARTBEAT criada com sucesso em {schema}")

                # Valida heartbeat
                cursor.execute(f'SELECT TO_INT(SECONDS_BETWEEN("LastUpdate", CURRENT_TIMESTAMP) / 60) AS DifMinutos FROM {schema}.SPS_BEAS_COMMON_HEARTBEAT WHERE ID = 1;')
                heartbeat = cursor.fetchone()[0]
                
                cursor.execute(f'CALL {schema}.SP_SPS_BEAS_COMMON_VALIDATION();')
                cursor.execute(f'DELETE FROM {schema}."BEAS_COMMON_INPUT" WHERE PARAMETER5 = \'SPS Common Check\' AND "Closed" = 1')
                
                if heartbeat > limit:
                    logger.warning(f"[{service}] [Beas Common] Common travada há ({heartbeat} min). Reiniciando e rodando UPDATE em {schema}...")
                    SystemMonitor.restart_service(service)
                    cursor.execute(f"""
                        UPDATE {schema}."BEAS_COMMON_INPUT"
                        SET "Closed" = 0
                        WHERE "TimeLife" BETWEEN (SELECT "LastUpdate" FROM "SPS_BEAS_COMMON_HEARTBEAT" WHERE ID = 1) AND CURRENT_TIMESTAMP
                        AND "Closed" = 1 AND "PARAMETER5" = 'SPS Common Check'
                    """)
                    conn.commit()
                    logger.info(f"[{service}] [Beas Common] Update em BEAS_COMMON_INPUT executado com sucesso em {schema}")
                else:
                    logger.info(f"[{service}] [Beas Common] Common validada há {heartbeat} min em {schema}")

        except Exception as e:
            logger.error(f"[{service}] [Beas Common] Erro crítico ao validar HEARTBEAT: {e}")
