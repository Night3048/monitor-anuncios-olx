"""Camada HTTP local: valida formulários e apresenta templates da interface.

As operações desta camada delegam persistência para config.py e pesquisas para
monitor.py. O servidor deve continuar ligado apenas a 127.0.0.1.
"""

import threading
import uuid
from urllib.parse import urlsplit

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from .config import load_config, save_config
from .monitor import check_once, status, status_lock
from .updater import VERSION, check_for_update, start_update

app = Flask(__name__)
# Uma chave nova por execução basta para mensagens flash locais; não são usados
# cookies persistentes nem uma sessão partilhada entre computadores.
app.secret_key = uuid.uuid4().hex
shutdown_event = threading.Event()


def _is_discord_webhook(value: str) -> bool:
    """Aceita apenas URLs HTTPS no formato de webhook do domínio oficial."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        path_parts = parsed.path.strip("/").split("/")
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and hostname == "discord.com"
        and port in (None, 443)
        and len(path_parts) == 4
        and path_parts[:2] == ["api", "webhooks"]
        and all(path_parts[2:])
    )


def _form_search(form, existing=None) -> dict:
    """Normaliza e valida campos comuns aos formulários de criação e edição."""
    name = form.get("name", "").strip()
    keyword = form.get("keyword", "").strip()
    site = form.get("site", "olx")
    if not name or not keyword:
        raise ValueError("Indica um nome e uma palavra-chave para a pesquisa.")
    if site not in ("olx", "wallapop"):
        raise ValueError("Escolhe OLX ou Wallapop.")
    if len(name) > 60 or len(keyword) > 120:
        raise ValueError("O nome pode ter até 60 caracteres e a palavra-chave até 120.")

    low = int(form["min_price"]) if form.get("min_price", "").strip() else None
    high = int(form["max_price"]) if form.get("max_price", "").strip() else None
    if low is not None and high is not None and low > high:
        raise ValueError("O preço mínimo tem de ser menor ou igual ao preço máximo.")
    if (low is not None and low < 0) or (high is not None and high < 0):
        raise ValueError("Os preços não podem ser negativos.")
    radius = int(form["radius_km"]) if form.get("radius_km", "").strip() else None
    if radius is not None and radius <= 0:
        raise ValueError("A distância tem de ser maior do que zero.")
    # Na edição, conserva o estado operacional e o histórico de links vistos.
    return {
        "id": existing.get("id") if existing else uuid.uuid4().hex[:8],
        "name": name,
        "site": site,
        "keyword": keyword,
        "exclude_keywords": [
            word.strip()
            for word in form.get("exclude_keywords", "").split(",")
            if word.strip()
        ],
        "min_price": low,
        "max_price": high,
        "center_location": form.get("center_location", "").strip() or None,
        "radius_km": radius,
        "enabled": existing.get("enabled", True) if existing else True,
        "seen_links": existing.get("seen_links", []) if existing else [],
        "last_checked": existing.get("last_checked") if existing else None,
    }


@app.get("/")
def index():
    """Mostra o painel principal com o estado atual e as pesquisas guardadas."""
    return render_template("index.html", cfg=load_config(), status=status, version=VERSION)


@app.post("/search/add")
def add_search():
    """Valida e acrescenta uma pesquisa nova à configuração local."""
    cfg = load_config()
    try:
        item = _form_search(request.form)
        cfg["searches"].append(item)
        save_config(cfg)
        flash("Pesquisa adicionada.", "success")
    except (ValueError, KeyError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("index"))


@app.route("/search/<search_id>/edit", methods=["GET", "POST"])
def edit_search(search_id):
    """Apresenta e guarda alterações de uma pesquisa existente."""
    cfg = load_config()
    old = next((s for s in cfg["searches"] if s["id"] == search_id), None)
    if not old:
        flash("Não foi possível encontrar essa pesquisa.", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            new = _form_search(request.form, old)
            cfg["searches"][cfg["searches"].index(old)] = new
            save_config(cfg)
            flash("Pesquisa atualizada.", "success")
            return redirect(url_for("index"))
        except (ValueError, KeyError) as exc:
            flash(str(exc), "error")
    return render_template("edit.html", search=old)


@app.post("/search/<search_id>/toggle")
def toggle_search(search_id):
    """Ativa ou pausa uma pesquisa sem apagar o seu histórico de anúncios."""
    cfg = load_config()
    for s in cfg["searches"]:
        if s["id"] == search_id:
            s["enabled"] = not s.get("enabled", True)
    save_config(cfg)
    return redirect(url_for("index"))


@app.post("/search/<search_id>/delete")
def delete_search(search_id):
    """Remove uma pesquisa e o respetivo histórico da configuração."""
    cfg = load_config()
    cfg["searches"] = [s for s in cfg["searches"] if s["id"] != search_id]
    save_config(cfg)
    flash("Pesquisa removida.", "success")
    return redirect(url_for("index"))


@app.post("/monitor/toggle")
def toggle_monitor():
    """Alterna a monitorização global sem alterar cada pesquisa individual."""
    cfg = load_config()
    cfg["master_enabled"] = not cfg.get("master_enabled", True)
    save_config(cfg)
    return redirect(url_for("index"))


@app.post("/settings")
def save_settings():
    """Guarda o webhook do Discord e limita o intervalo a valores seguros."""
    cfg = load_config()
    webhook = request.form.get("webhook", "").strip()
    try:
        interval = max(60, min(86400, int(request.form.get("interval", "300"))))
    except ValueError:
        flash("Escolhe uma frequência válida.", "error")
        return redirect(url_for("index"))
    if webhook and not _is_discord_webhook(webhook):
        flash("O URL do webhook não parece ser válido.", "error")
    else:
        cfg.update(discord_webhook=webhook, interval_seconds=interval)
        save_config(cfg)
        flash("Definições guardadas.", "success")
    return redirect(url_for("index"))


@app.post("/monitor/check")
def manual_check():
    """Inicia uma verificação manual em segundo plano para não bloquear a página."""
    def run_manual_check():
        with status_lock:
            status["running"] = True
            status["message"] = "A verificar as pesquisas…"
        check_once()

    threading.Thread(target=run_manual_check, daemon=True, name="verificacao-manual").start()
    return redirect(url_for("index"))


@app.get("/api/status")
def api_status():
    """Fornece ao painel o estado do monitor e do verificador de versões."""
    info = check_for_update()
    with status_lock:
        payload = dict(status)
    payload["update"] = info
    return jsonify(payload)


@app.post("/updates/install")
def install_update():
    """Inicia a transferência da atualização disponível, se houver uma."""
    if start_update():
        return "", 204
    return "", 409


@app.post("/app/exit")
def exit_app():
    """Pede ao ponto de entrada que encerre o servidor de forma ordenada."""
    threading.Timer(0.5, shutdown_event.set).start()
    return render_template("exit.html")
