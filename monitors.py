import os
import subprocess
import socket
import psutil
import time
import requests
import shutil
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
                
                last_recorded = ""
                if os.path.exists(HanaSystemMonitor.STATE_FILE):
                    with open(HanaSystemMonitor.STATE_FILE, "r", encoding="utf-8") as f:
                        last_recorded = f.read().strip()
                
                if diff_minutes >= 5:
                    if last_recorded != start_time_str:
                        logger.warning(f"[HANA Global] HANA rodando há {diff_minutes} minutos (Startup: {start_time_str}). Iniciando restart em MASSA nos serviços BEAS...")
                        
                        for svc in beas_services:
                            SystemMonitor.restart_service(svc.service_name)
                        
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
    def clean_beas_temp():
        """Limpa a pasta C:\\ProgramData\\beas\\temp em caso de falha."""
        temp_dir = r"C:\ProgramData\beas\temp"
        if not os.path.exists(temp_dir):
            return
            
        logger.warning(f"[Sistema] Limpando diretório temporário: {temp_dir}")
        try:
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    logger.debug(f"[Sistema] Erro ao deletar {item_path}: {e}")
            logger.info(f"[Sistema] Limpeza do {temp_dir} concluída com sucesso.")
        except Exception as e:
            logger.error(f"[Sistema] Erro crítico ao limpar {temp_dir}: {e}")

    @staticmethod
    def _start_service_with_retry(service_name: str):
        """Inicia o serviço e, se falhar, limpa o temp do beas e tenta de novo."""
        logger.info(f"[{service_name}] [SC] ▶️ Iniciando serviço: {service_name}")
        subprocess.run(["sc", "start", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Aguarda até 5 segundos para confirmar se subiu
        started = False
        for _ in range(5):
            try:
                if psutil.win_service_get(service_name).status() == 'running':
                    started = True
                    break
            except Exception:
                pass
            time.sleep(1)
            
        if not started:
            logger.error(f"[{service_name}] [SC] ❌ Falha detectada ao iniciar. Limpando temp...")
            SystemMonitor.clean_beas_temp()
            
            logger.info(f"[{service_name}] [SC] ▶️ Tentando iniciar serviço novamente após limpeza...")
            subprocess.run(["sc", "start", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            for _ in range(5):
                try:
                    if psutil.win_service_get(service_name).status() == 'running':
                        logger.info(f"[{service_name}] [SC] ✅ Serviço iniciado com sucesso após limpeza!")
                        break
                except Exception:
                    pass
                time.sleep(1)

    @staticmethod
    def check_multiple_pids(service_name: str) -> bool:
        """
        Verifica para cada beasService se existe mais de um PID no Windows.
        Se tiver mais de um PID, usa psutil para matá-los e depois inicia o serviço novamente.
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
                    
                    exe_name = os.path.basename(p_exe).lower()
                    
                    if service_name.lower() in cmd_str_clean or binpath_clean in cmd_str_clean:
                        matching_processes[p.info['pid']] = exe_name
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            from collections import Counter
            exe_counts = Counter(matching_processes.values())
            
            has_duplicates = exe_counts.get('beas.exe', 0) > 1
            
            if has_duplicates:
                pids_to_kill = list(matching_processes.keys())
                logger.warning(f"[{service_name}] [Monitor] ⚠️ Foram detectados processos duplicados para o serviço: {dict(exe_counts)}")
                for pid in pids_to_kill:
                    logger.warning(f"[{service_name}] [Monitor] 🗡️ Forçando finalização nativa no PID {pid} via psutil...")
                    try:
                        psutil.Process(pid).kill()
                    except psutil.NoSuchProcess:
                        pass
                
                subprocess.run(["sc", "stop", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Aguarda liberação do SO antes do start
                for _ in range(10):
                    try:
                        if psutil.win_service_get(service_name).status() == 'stopped':
                            break
                    except Exception:
                        pass
                    time.sleep(1)

                SystemMonitor._start_service_with_retry(service_name)
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
                logger.warning(f"[{service_name}] [Monitor] 🗡️ Forçando finalização nativa no PID {pid} via psutil...")
                try:
                    p = psutil.Process(pid)
                    p.kill()
                    p.wait(timeout=3)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
                    pass
            else:
                logger.info(f"[{service_name}] [Monitor] 🤷‍♂️ Serviço não possuía PID ativo (já parado).")
                
            subprocess.run(["sc", "stop", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Smart-Wait: Aguarda até o serviço de fato ser reportado como 'stopped' pelo Windows
            # para evitar que suba novamente com a porta ainda engasgada
            for _ in range(10):
                try:
                    if psutil.win_service_get(service_name).status() == 'stopped':
                        break
                except Exception:
                    pass
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"[{service_name}] [Monitor] ❌ Erro ao gerenciar serviço: {e}")

        SystemMonitor._start_service_with_retry(service_name)

    @staticmethod
    def disable_service(service_name: str):
        logger.warning(f"[{service_name}] [SC] 🛑 Desativando o serviço do Windows permanentemente: {service_name}")
        
        try:
            service = psutil.win_service_get(service_name)
            pid = service.pid()
            if pid and pid > 0:
                logger.warning(f"[{service_name}] [Monitor] 🗡️ Matando PID {pid} via psutil antes de desativar...")
                try:
                    psutil.Process(pid).kill()
                except psutil.NoSuchProcess:
                    pass
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
                
                cursor.execute('SELECT COUNT(1) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?', (schema,))
                if cursor.fetchone()[0] == 0:
                    logger.error(f"[{service}] [Atividades] Banco de Dados '{schema}' inexistente no HANA. Desativando o serviço...")
                    SystemMonitor.disable_service(service)
                    return
                    
                cursor.execute(f'SET SCHEMA "{schema}";')
                cursor.execute("""
                    SELECT COUNT(1)
                    FROM "BEAS_SYS_SERVER"
                    WHERE "BEZEICHNUNG" = ?;
                """, ('BEAS - Gerenciamento de Serviço',))
                valida = cursor.fetchone()[0]
                
                if valida > 0:
                    cursor.execute("""
                        SELECT TO_INT(SECONDS_BETWEEN("STATISTIC_LASTSTART", CURRENT_TIMESTAMP) / 60) AS DIF_MINUTOS 
                        FROM "BEAS_SYS_SERVER"
                        WHERE "BEZEICHNUNG" = ?;
                    """, ('BEAS - Gerenciamento de Serviço',))
                    diff = cursor.fetchone()[0]
                    if diff >= 2:
                        logger.warning(f"[{service}] [Atividades] Última execução >= 2 min ({diff} min). Reiniciando {service} em {schema}...")
                        SystemMonitor.restart_service(service)
                    else:
                        if diff < 0:
                            diff = 0
                        logger.info(f"[{service}] [Atividades] Última execução validada há {diff} min em {schema}")
                else:
                    logger.warning(f"[{service}] [Atividades] Tabela BEAS_SYS_SERVER não possui registros para monitoramento em {schema}.")
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
                
                cursor.execute('SELECT COUNT(1) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?', (schema,))
                if cursor.fetchone()[0] == 0:
                    logger.error(f"[{service}] [Beas Common] Banco de Dados '{schema}' inexistente no HANA. Desativando o serviço...")
                    SystemMonitor.disable_service(service)
                    return
                
                cursor.execute('SELECT COUNT(1) FROM "SYS"."TABLES" WHERE "SCHEMA_NAME" = ? AND "TABLE_NAME" = ?', (schema, 'SPS_BEAS_COMMON_HEARTBEAT'))
                cnt = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(1) FROM "SYS"."PROCEDURES" WHERE "SCHEMA_NAME" = ? AND "PROCEDURE_NAME" = ?', (schema, 'SP_SPS_BEAS_COMMON_VALIDATION'))
                cnt2 = cursor.fetchone()[0]
                
                cursor.execute(f'SET SCHEMA "{schema}";')
                
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

                cursor.execute(f'SELECT TO_INT(SECONDS_BETWEEN("LastUpdate", CURRENT_TIMESTAMP) / 60) AS DifMinutos FROM "{schema}"."SPS_BEAS_COMMON_HEARTBEAT" WHERE ID = 1;')
                heartbeat = cursor.fetchone()[0]
                
                cursor.execute(f'CALL "{schema}"."SP_SPS_BEAS_COMMON_VALIDATION"();')
                
                cursor.execute('DELETE FROM "BEAS_COMMON_INPUT" WHERE "PARAMETER5" = ? AND "Closed" = ?', ('SPS Common Check', 1))
                
                if heartbeat > limit:
                    logger.warning(f"[{service}] [Beas Common] Common travada há ({heartbeat} min). Reiniciando e rodando UPDATE em {schema}...")
                    SystemMonitor.restart_service(service)
                    cursor.execute("""
                        UPDATE "BEAS_COMMON_INPUT"
                        SET "Closed" = 0
                        WHERE "TimeLife" BETWEEN (SELECT "LastUpdate" FROM "SPS_BEAS_COMMON_HEARTBEAT" WHERE ID = 1) AND CURRENT_TIMESTAMP
                        AND "Closed" = 1 AND "PARAMETER5" = ?
                    """, ('SPS Common Check',))
                    conn.commit()
                    logger.info(f"[{service}] [Beas Common] Update em BEAS_COMMON_INPUT executado com sucesso em {schema}")
                else:
                    logger.info(f"[{service}] [Beas Common] Common validada há {heartbeat} min em {schema}")

        except Exception as e:
            logger.error(f"[{service}] [Beas Common] Erro crítico ao validar HEARTBEAT: {e}")
