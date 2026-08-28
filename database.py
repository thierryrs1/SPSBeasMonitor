import logging
from contextlib import contextmanager
from hdbcli import dbapi

from config import config
from logger import logger


class DatabaseClient:
    """
    Encapsula a comunicacao com SAP HANA.
    Usa uma unica conexao compartilhada para evitar delays.
    """

    def __init__(self):
        self.server = config.DB_SERVER
        self.user = config.DB_USERNAME
        self.password = config.DB_PASSWORD
        self.port = config.DB_PORT

        self._shared_conn = None
        self._connection_failed = False

    @contextmanager
    def get_connection(self):
        """
        Retorna a conexao ativa com o HANA.
        Se falhar na 1a vez, aborta as proximas imediatamente.
        """
        if self._connection_failed:
            raise ConnectionError("Falha previa com o banco. Pulando.")

        try:
            if self._shared_conn is None:
                host = self.server
                port = self.port
                if ":" in self.server:
                    host, port_str = self.server.split(":")
                    port = int(port_str)

                self._shared_conn = dbapi.connect(
                    address=host,
                    port=port,
                    user=self.user,
                    password=self.password
                )

            yield self._shared_conn

        except Exception as e:
            if not self._connection_failed:
                logger.error(f"[Database] Erro no HANA ({self.server}): {e}")
            self._connection_failed = True
            raise


db_client = DatabaseClient()
