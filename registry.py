import winreg
from dataclasses import dataclass
from typing import Optional
from logger import logger

@dataclass
class BeasService:
    """Representa e tipa os dados de um serviço BEAS obtidos via Regedit."""
    service_name: str
    display_name: Optional[str] = None
    html_indexname: Optional[int] = None
    mssql_database: Optional[str] = None
    service_common: Optional[str] = None
    service_html: Optional[str] = None
    service_order: Optional[str] = None
    html_comm: Optional[str] = None
    web_ip: Optional[str] = None

class RegistryScanner:
    """Isola a leitura do Regedit do Windows para obtenção das configurações dos serviços BEAS."""
    
    @staticmethod
    def get_beas_services() -> list[BeasService]:
        services = []
        path = r"SYSTEM\CurrentControlSet\Services"

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        i += 1

                        if subkey_name.lower().startswith("beasservice"):
                            svc = RegistryScanner._read_service_info(key, subkey_name)
                            services.append(svc)
                    except OSError:
                        break  # Fim das subkeys
        except Exception as e:
            logger.error(f"[Registry] ❌ Erro geral ao ler o registro: {e}")

        return services

    @staticmethod
    def _read_service_info(parent_key, subkey_name: str) -> BeasService:
        info = {
            "DisplayName": None,
            "html_indexname": None,
            "mssql_database": None,
            "service_common": None,
            "service_html": None,
            "service_order": None,
            "html_comm": None,
        }
        web_ip = None

        try:
            with winreg.OpenKey(parent_key, subkey_name) as subkey:
                for field in info.keys():
                    try:
                        value, _ = winreg.QueryValueEx(subkey, field)
                        info[field] = value
                    except FileNotFoundError:
                        pass
                
                # Tratar projectfolder para obter web_ip se necessário futuramente, mas hoje extraí o IP
                try:
                    pf, _ = winreg.QueryValueEx(subkey, "projectfolder")
                    if pf:
                        web_ip = pf.lstrip("\\").split("\\")[0]
                except FileNotFoundError:
                    pass

        except Exception as e:
            logger.debug(f"[Registry] Erro ao ler chave {subkey_name}: {e}")

        # Tratamento seguro da porta html_indexname para integer (essencial para binds socket)
        html_indexname_int = None
        if info["html_indexname"]:
            try:
                html_indexname_int = int(str(info["html_indexname"]).strip())
            except ValueError:
                pass

        return BeasService(
            service_name=subkey_name,
            display_name=info["DisplayName"],
            html_indexname=html_indexname_int,
            mssql_database=info["mssql_database"],
            service_common=info["service_common"],
            service_html=info["service_html"],
            service_order=info["service_order"],
            html_comm=info["html_comm"],
            web_ip=web_ip
        )
