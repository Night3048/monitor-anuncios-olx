"""Configuração e persistência local do Procurador de Anúncios.

Os dados mutáveis vivem em ``%APPDATA%\\ProcuradorAnuncios``. Os recursos
imutáveis incluídos na instalação, como as pesquisas iniciais, são lidos de
outra pasta para que reinstalar a aplicação não apague o estado do utilizador.
"""

import json
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

APP_NAME = "ProcuradorAnuncios"

# Este lock protege leituras e escritas feitas por threads dentro deste processo.
CONFIG_LOCK = threading.RLock()


def app_root() -> Path:
    """Devolve a pasta da aplicação ou do executável empacotado."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Devolve a pasta de recursos, incluindo a extração temporária do PyInstaller."""
    return Path(getattr(sys, "_MEIPASS", app_root()))


def data_dir() -> Path:
    """Cria e devolve a pasta de dados do utilizador no perfil do Windows."""
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    directory = base / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


CONFIG_PATH = data_dir() / "config.json"
CACHE_PATH = data_dir() / "geocode_cache.json"


def _default_config() -> dict[str, Any]:
    """Cria um objeto novo para não partilhar listas mutáveis entre pedidos."""
    return {
        "discord_webhook": "",
        "interval_seconds": 300,
        "master_enabled": True,
        "searches": [],
    }


def _validate_config(value: Any) -> dict[str, Any]:
    """Confirma o formato mínimo antes de a configuração chegar às rotas."""
    if not isinstance(value, dict):
        raise ValueError("A raiz da configuração tem de ser um objeto JSON.")

    config = {**_default_config(), **value}
    searches = config["searches"]
    if not isinstance(searches, list):
        raise ValueError("A lista de pesquisas não é válida.")
    if not all(isinstance(search, dict) for search in searches):
        raise ValueError("Uma ou mais pesquisas não são objetos válidos.")

    # Normaliza preferências antigas ou editadas manualmente antes do monitor.
    config["discord_webhook"] = (
        config["discord_webhook"] if isinstance(config["discord_webhook"], str) else ""
    )
    config["master_enabled"] = (
        config["master_enabled"] if isinstance(config["master_enabled"], bool) else True
    )
    try:
        interval = int(config["interval_seconds"])
    except (TypeError, ValueError):
        interval = 300
    config["interval_seconds"] = max(60, min(interval, 86400))

    for search in searches:
        search.setdefault("enabled", True)
        search.setdefault("exclude_keywords", [])
        search.setdefault("seen_links", [])
        search.setdefault("last_checked", None)
        if not isinstance(search["exclude_keywords"], list):
            search["exclude_keywords"] = []
        if not isinstance(search["seen_links"], list):
            search["seen_links"] = []
    return config


def _load_initial_config() -> dict[str, Any]:
    """Lê as pesquisas migradas que acompanham a instalação, se existirem."""
    initial_path = resource_root() / "data" / "initial_config.json"
    try:
        initial = json.loads(initial_path.read_text(encoding="utf-8"))
        return _validate_config(initial)
    except (OSError, json.JSONDecodeError, ValueError):
        # Uma semente ausente ou inválida não deve impedir a app de arrancar.
        return _default_config()


def load_config() -> dict[str, Any]:
    """Carrega a configuração, migra a configuração inicial e aplica defaults.

    Um ficheiro de configuração danificado é preservado como ``.broken.json``
    antes de iniciar com defaults, em vez de bloquear o arranque da aplicação.
    """
    with CONFIG_LOCK:
        if not CONFIG_PATH.exists():
            save_config(_load_initial_config())

        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return _validate_config(raw)
        except (OSError, json.JSONDecodeError, ValueError):
            broken_path = CONFIG_PATH.with_suffix(".broken.json")
            try:
                CONFIG_PATH.replace(broken_path)
            except OSError:
                # Se o ficheiro estiver bloqueado, ainda tentamos iniciar com defaults.
                pass
            defaults = _default_config()
            save_config(defaults)
            return defaults


def save_config(config: dict[str, Any]) -> None:
    """Guarda JSON por substituição atómica para evitar ficheiros parciais."""
    with CONFIG_LOCK:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = CONFIG_PATH.with_suffix(".tmp")
        serialized = json.dumps(config, ensure_ascii=False, indent=2)
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(CONFIG_PATH)


def load_cache() -> dict[str, Any]:
    """Lê a cache geográfica; uma cache ausente ou inválida começa vazia."""
    try:
        value = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_cache(cache: dict[str, Any]) -> None:
    """Guarda a cache geográfica por substituição atómica."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = CACHE_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_path.replace(CACHE_PATH)


def update_search(search_id: str, update: Callable[[dict[str, Any]], None]) -> bool:
    """Atualiza uma pesquisa dentro de uma única secção crítica.

    ``update`` recebe o dicionário da pesquisa e pode alterar os campos que
    pertencem ao monitor, sem sobrescrever alterações feitas pela interface.
    Devolve False se a pesquisa já tiver sido removida.
    """
    with CONFIG_LOCK:
        config = load_config()
        search = next((item for item in config["searches"] if item.get("id") == search_id), None)
        if search is None:
            return False
        update(search)
        save_config(config)
        return True
