"""Arranque da aplicação e ligação entre o monitor, o servidor e o navegador.

Este módulo mantém o ponto de entrada pequeno: valida o sistema operativo,
prepara a configuração, inicia o monitor e serve a interface apenas em loopback.
"""

import sys
import threading
import webbrowser

from werkzeug.serving import make_server

from procurador.config import load_config
from procurador.monitor import start_monitor
from procurador.updater import start_update_check
from procurador.web import app, shutdown_event


def _open_dashboard(url: str) -> None:
    """Abre a página principal no navegador predefinido do utilizador."""
    webbrowser.open(url)


def main() -> None:
    """Inicia o serviço local até o utilizador escolher «Sair»."""
    if sys.platform != "win32":
        raise SystemExit("O Procurador de Anúncios está disponível apenas para Windows.")

    # A configuração e os dados do utilizador vivem em %APPDATA%, não na pasta
    # de instalação, para que uma atualização não apague pesquisas ou credenciais.
    load_config()
    # Procura uma versão nova em segundo plano sem atrasar o painel local.
    start_update_check()
    start_monitor()

    # O servidor escolhe uma porta livre e liga-se só ao próprio computador.
    # Não fica acessível a outros dispositivos na rede local.
    server = make_server("127.0.0.1", 0, app, threaded=True)
    url = f"http://127.0.0.1:{server.server_port}/"
    threading.Timer(1.0, _open_dashboard, args=(url,)).start()

    server_thread = threading.Thread(target=server.serve_forever, name="web-server", daemon=True)
    server_thread.start()

    try:
        # A rota /app/exit sinaliza este evento; o servidor é então encerrado
        # ordenadamente, sem terminar o processo à força.
        shutdown_event.wait()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)


if __name__ == "__main__":
    main()
