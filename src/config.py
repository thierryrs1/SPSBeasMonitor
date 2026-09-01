import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

@dataclass(frozen=True)
class AppConfig:
    DBTYPE: str = os.getenv("DBTYPE", "HANA")
    DB_SERVER: str = os.getenv("DB_SERVER", "")
    DB_USERNAME: str = os.getenv("DB_USERNAME", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_PORT: str = os.getenv("DB_PORT", "")
    COMMON_LIMIT_TIME: int = int(os.getenv("COMMON_LIMIT_TIME", "10"))
    
    CHECK_BSL: bool = os.getenv("CHECK_BSL", "False").lower() in ("true", "1", "yes")
    CHECK_WEB: bool = os.getenv("CHECK_WEB", "False").lower() in ("true", "1", "yes")
    CHECK_SERVER: bool = os.getenv("CHECK_SERVER", "False").lower() in ("true", "1", "yes")
    CHECK_COMMON: bool = os.getenv("CHECK_COMMON", "False").lower() in ("true", "1", "yes")
    CHECK_MULTIPLE_PIDS: bool = os.getenv("CHECK_MULTIPLE_PIDS", "False").lower() in ("true", "1", "yes")

# Instância global das configurações
config = AppConfig()

