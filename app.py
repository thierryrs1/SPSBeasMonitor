import psutil
from logger import logger
from registry import RegistryScanner
from monitors import SystemMonitor, BeasMonitor, HanaSystemMonitor
from config import config

def main():
    logger.info("Iniciando rotina de checagem do SPSBeasMonitor...")
    
    SystemMonitor.monitor_ram(threshold=80)
    
    all_beas_services = RegistryScanner.get_beas_services()
    
    beas_services = []
    for svc in all_beas_services:
        try:
            status = psutil.win_service_get(svc.service_name).status()
            if status == 'running':
                beas_services.append(svc)
        except Exception as e:
            pass # Ignorando serviços que não existem ou com acesso negado para manter o log limpo

    if not beas_services:
        logger.warning("[App] Nenhum serviço BEAS em execução ('Running') foi encontrado!")
        logger.info("-" * 100)
        return
        
    HanaSystemMonitor.check_startup_and_restart(beas_services)
        
    beas_monitor = BeasMonitor()

    for svc in beas_services:
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
            beas_monitor.check_common_heartbeat(svc, int(config.COMMON_LIMIT_TIME))

    logger.info("Rotina de checagem finalizada.")
    logger.info("-" * 100)

if __name__ == "__main__":
    main()
