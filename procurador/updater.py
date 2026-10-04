"""Verificação e instalação de atualizações publicadas em GitHub Releases.

O repositório é inserido no módulo build_info.py durante a compilação. Não se
define um destino por omissão: cada publicação tem de apontar para o repositório
do autor da aplicação.
"""
import json
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import requests

from .config import app_root

try:
    from .build_info import VERSION, GITHUB_REPOSITORY
except ImportError:
    VERSION = "1.0.0"
    GITHUB_REPOSITORY = ""
_result = {"state": "not_configured", "current": VERSION, "latest": None, "message": ""}
_lock = threading.Lock()
_check_lock = threading.Lock()
_checked_at = 0
_update_in_progress = False
UPDATE_CHECK_INTERVAL = 6 * 60 * 60
API_TIMEOUT_SECONDS = 10


def _version_parts(value):
    """Converte a parte numérica de uma versão (ex.: v1.2.3) em tuplo."""
    match = re.match(r"^(\d+(?:\.\d+)*)", str(value).strip().lstrip("v"))
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _is_newer(candidate, current):
    """Compara versões simples sem depender de uma biblioteca adicional."""
    left, right = _version_parts(candidate), _version_parts(current)
    if not left or not right:
        return False
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))


def _check_for_update(force: bool = False):
    """Consulta a release mais recente, com opção de forçar no arranque."""
    global _checked_at
    if not GITHUB_REPOSITORY:
        _result.update(state="not_configured", message="As atualizações ficam disponíveis quando o publicador configurar o canal de versões.")
        return dict(_result)
    if not force and time.time() - _checked_at < UPDATE_CHECK_INTERVAL:
        return dict(_result)
    try:
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest",
            timeout=API_TIMEOUT_SECONDS,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ProcuradorAnuncios",
            },
        )
        if response.status_code == 404:
            _result.update(
                state="error",
                latest=None,
                message="Não encontrei uma release pública; confirma o repositório configurado.",
            )
            _checked_at = time.time()
            return dict(_result)
        response.raise_for_status()
        release = response.json()
        latest = release.get("tag_name", "").lstrip("v")
        newer = _is_newer(latest, VERSION)
        # Só aceitamos o instalador nomeado; não arriscamos executar um .exe
        # diferente que possa existir entre os restantes artefactos da release.
        installer = next((a["browser_download_url"] for a in release.get("assets", [])
                          if a.get("name", "").lower().endswith(".exe") and "setup" in a.get("name", "").lower()), None)
        if newer and installer:
            _result.update(
                state="available",
                latest=latest,
                url=installer,
                message=f"A versão {latest} está pronta para instalar.",
            )
        elif newer:
            _result.update(
                state="error",
                latest=latest,
                url=None,
                message="Há uma versão nova, mas a release não inclui o instalador Setup.exe.",
            )
        else:
            _result.update(
                state="current",
                latest=latest or VERSION,
                url=None,
                message="Está a usar a versão mais recente.",
            )
        _checked_at = time.time()
    except (requests.RequestException, ValueError):
        _result.update(state="error", message="Não foi possível procurar atualizações. Verifique a ligação à Internet.")
        _checked_at = time.time()
    return dict(_result)


def check_for_update(force: bool = False):
    """Evita pedidos simultâneos à API e devolve o estado mais recente."""
    if not _check_lock.acquire(blocking=False):
        return dict(_result)
    try:
        return _check_for_update(force=force)
    finally:
        _check_lock.release()


def start_update_check() -> None:
    """Verifica o canal de versões em segundo plano ao abrir a aplicação."""
    threading.Thread(
        target=check_for_update,
        kwargs={"force": True},
        daemon=True,
        name="verificacao-atualizacoes",
    ).start()


def start_update():
    """Transfere o instalador oficial e inicia a atualização silenciosa."""
    global _update_in_progress
    with _lock:
        if _update_in_progress:
            return False
        info = dict(_result)
        if info.get("state") != "available" or not info.get("url"):
            return False
        _update_in_progress = True

        def install() -> None:
            global _update_in_progress
            try:
                response = requests.get(info["url"], timeout=120, stream=True)
                response.raise_for_status()
                path = Path(tempfile.gettempdir()) / "ProcuradorAnuncios-Update.exe"
                with path.open("wb") as out:
                    for chunk in response.iter_content(1024 * 128):
                        if chunk:
                            out.write(chunk)
                subprocess.Popen([str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                                 cwd=str(app_root()), close_fds=True)
            except (OSError, requests.RequestException) as exc:
                _result.update(state="error", message=f"Não foi possível instalar a atualização: {exc}")
            finally:
                with _lock:
                    _update_in_progress = False
        threading.Thread(target=install, daemon=True).start()
        return True
