from contextlib import contextmanager
from hdbcli import dbapi
from config import config
from logger import logger

class DatabaseClient:
    """Encapsula a comunicação com SAP HANA usando Context Managers para prevenir vazamentos de conexão."""
    
    def __init__(self):
        self.server = config.DB_SERVER
        self.user = config.DB_USERNAME
        self.password = config.DB_PASSWORD
        self.port = config.DB_PORT

    @contextmanager
    def get_connection(self):
        """Retorna uma conexão ativa com o HANA. Gerencia automaticamente o fechamento."""
        conn = None
        try:
            host = self.server
            port = self.port
            if ":" in self.server:
                host, port_str = self.server.split(":")
                port = int(port_str)
            else:
                port = int(port) if port else 30015
            
            conn = dbapi.connect(
                address=host,
                port=port,
                user=self.user,
                password=self.password
            )
        except Exception as e:
            logger.error(f"[Database] ❌ Erro ao conectar no HANA ({self.server}): {e}")
            raise
            
        try:
            yield conn
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"[Database] ❌ Erro ao fechar conexão com HANA: {e}")

db_client = DatabaseClient()
