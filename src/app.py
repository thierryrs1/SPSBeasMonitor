import psutil
from logger import logger
from registry import RegistryScanner
from monitors import SystemMonitor, BeasMonitor, HanaSystemMonitor
from config import config

def main():
    # Separador invertido (a primeira linha que enviamos desce no TXT se prepended, 
    # então enviamos um divisor ao fim da execução para ficar no topo do log)
    
    logger.info("Iniciando rotina de checagem do SPSBeasMonitor...")
    
    # 1. Valida RAM e infraestruturas do Host
    SystemMonitor.monitor_ram(threshold=80)
    
    # 2. Carrega todos os serviços instalados no registro do Windows
    all_beas_services = RegistryScanner.get_beas_services()
    
    # 2.1 Filtra para manter na checagem apenas os serviços que estão em execução (Ignora os "Parados")
    beas_services = []
    for svc in all_beas_services:
        try:
            if psutil.win_service_get(svc.service_name).status() == 'running':
                beas_services.append(svc)
        except Exception:
            pass

    if not beas_services:
        logger.warning("[App] Nenhum serviço BEAS em execução ('Running') foi encontrado!")
        logger.info("-" * 100)
        return
        
    # 2.5 Lógica Global de Monitoramento de Startup do Banco (Restart em Massa)
    HanaSystemMonitor.check_startup_and_restart(beas_services)
        
    # 3. Instancia os módulos de negócio
    beas_monitor = BeasMonitor()

    # 4. Processa por serviço do BEAS as rotinas ativadas
    for svc in beas_services:
        # 4.1 Validação de múltiplos PIDs no Windows
        if config.CHECK_MULTIPLE_PIDS:
            if SystemMonitor.check_multiple_pids(svc.service_name):
                continue
            
        if config.CHECK_BSL:
            beas_monitor.check_bsl_odata(svc)
            
        if config.CHECK_WEB:
            beas_monitor.check_web_portal(svc)
            
        if config.CHECK_SERVER:
            beas_monitor.check_system_server(svc)
            
        if config.CHECK_COMMON:
            beas_monitor.check_common_heartbeat(svc, config.COMMON_LIMIT_TIME)

    logger.info("Rotina de checagem finalizada.")
    logger.info("-" * 100)

if __name__ == "__main__":
    main()
