import os
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime

class PrependDailyFileHandler(logging.Handler):
    def __init__(self, log_dir, base_name="monitor", backup_count=7, encoding="utf-8"):
        super().__init__()
        self.log_dir = log_dir
        self.base_name = base_name
        self.backup_count = backup_count
        self.encoding = encoding
        os.makedirs(log_dir, exist_ok=True)

    def _get_current_file(self):
        # Ex: "09-04-2026_monitor.log"
        today = datetime.datetime.now().strftime("%d-%m-%Y")
        return os.path.join(self.log_dir, f"{today}_{self.base_name}.log")

    def _cleanup_old_logs(self):
        limit_date = datetime.datetime.now() - datetime.timedelta(days=self.backup_count)
        for filename in os.listdir(self.log_dir):
            if filename.endswith(".log") and self.base_name in filename:
                try:
                    # Extrai a data da string no formato "DD-MM-YYYY_monitor.log"
                    date_str = filename.split("_")[0]
                    file_date = datetime.datetime.strptime(date_str, "%d-%m-%Y")
                    if file_date < limit_date:
                        os.remove(os.path.join(self.log_dir, filename))
                except ValueError:
                    continue

    def emit(self, record):
        try:
            msg = self.format(record) + "\n"
            log_file = self._get_current_file()
            
            old_content = ""
            if os.path.exists(log_file):
                with open(log_file, "r", encoding=self.encoding) as f:
                    old_content = f.read()

            with open(log_file, "w", encoding=self.encoding) as f:
                f.write(msg + old_content)

            self._cleanup_old_logs()
        except Exception:
            self.handleError(record)

import re

class TableFormatter(logging.Formatter):
    def format(self, record):
        original_msg = str(record.msg)
        
        # Ignora a formatação nos separadores de linha "--" par garantir espaçamento vertical limpo
        if "----------" in original_msg:
            return super().format(record)
            
        # 1. Escolhe o Emoji Mestre daquela linha pela severidade do log
        if record.levelno == logging.INFO:
            emoji = "✅"
        elif record.levelno == logging.WARNING:
            emoji = "⚠️"
        elif record.levelno >= logging.ERROR:
            emoji = "❌"
        else:
            emoji = "ℹ️"
            
        # 2. Desinfeta as mensagems antigas que já possuíam emojis hardcoded pelos desenvolvedores
        for e in ["✅", "⚠️", "❌", "🛑", "🔄"]:
            original_msg = original_msg.replace(e, "")
            
        original_msg = original_msg.strip()
        
        # 3. Mágica do Regex para extrair as Tags [Substantivo] [Verbo] Mensagem real.
        match = re.match(r"^\[(.*?)\]\s*(?:\[(.*?)\])?\s*(.*)$", original_msg)
        
        if match:
            col1 = match.group(1).strip()
            col2 = match.group(2).strip() if match.group(2) else "-"
            msg = match.group(3).strip()
        else:
            col1 = "Global"
            col2 = "-"
            msg = original_msg
            
        # Previne espaços múltiplos no meio das mensagens que quebravam layout
        msg = " ".join(msg.split())
        
        # 4. Formata a tabela delimitando o preenchimento de caracteres fixos ljust()
        # Coluna 1 (BeasService / Server): 15 slots
        # Coluna 2 (Módulo Atuante): 13 slots
        table_msg = f"{emoji} | {col1[:15].ljust(15)} | {col2[:13].ljust(13)} | {msg}"
        
        record.msg = table_msg
        return super().format(record)

def setup_logger():
    log_dir = "logs"
    
    logger = logging.getLogger("SPSBeasMonitor")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        file_handler = PrependDailyFileHandler(log_dir=log_dir, backup_count=7)
        console_handler = logging.StreamHandler()
        
        # Injeta Tabela Inteligente Colorida e Alinhada para Console e TXT
        formatter = TableFormatter(
            fmt="[%(asctime)s] %(message)s",
            datefmt="%d/%m/%Y %H:%M:%S"
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logger()
