"""Pesquisa anúncios, aplica filtros e envia novidades ao Discord.

O monitor corre fora dos pedidos HTTP. Este módulo não conhece os formulários
nem HTML; recebe objetos de pesquisa já normalizados e devolve anúncios simples.
"""

import re
import threading
import time
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt
from typing import Any

import requests
from bs4 import BeautifulSoup

from .config import load_cache, save_cache, load_config, update_search

try:
    from wallapy import check_wallapop
except ImportError:
    check_wallapop = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Referer": "https://www.olx.pt/",
}
olx_session = requests.Session()
olx_session.headers.update(HEADERS)
status: dict[str, Any] = {
    "last_run": None,
    "message": "A preparar a primeira verificação…",
    "running": False,
    "new_count": 0,
    "errors": [],
}
status_lock = threading.Lock()
geocode_lock = threading.Lock()
check_lock = threading.Lock()
monitor_start_lock = threading.Lock()
monitor_thread: threading.Thread | None = None


def _price_ok(text: str | None, low: int | None, high: int | None) -> bool:
    """Confirma o intervalo de preço a partir do texto apresentado no anúncio.

    Se o site não fornecer um preço legível, não elimina o anúncio: o filtro
    do próprio site já foi aplicado e não há dados suficientes para o rejeitar.
    """
    if low is None and high is None or not text:
        return True
    digits = re.sub(r"[^\d]", "", str(text))
    if not digits:
        return True
    value = int(digits)
    return (low is None or value >= int(low)) and (high is None or value <= int(high))


def _excluded(title: str, words: list[str] | None) -> bool:
    """Devolve False quando o título contém alguma palavra excluída."""
    value = title.casefold()
    return not any(word.strip() and word.strip().casefold() in value for word in (words or []))


def _geocode(place: str | None) -> tuple[float, float] | None:
    """Converte um local português em coordenadas e respeita o limite do serviço.

    Resultados positivos e pesquisas sem correspondência ficam em cache. Falhas
    de rede não são guardadas, para que uma tentativa futura possa recuperar.
    """
    if not place:
        return None
    key = place.strip().casefold()
    with geocode_lock:
        cache = load_cache()
        if key in cache:
            return tuple(cache[key]) if cache[key] else None
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": place, "format": "json", "limit": 1, "countrycodes": "pt"},
                headers={"User-Agent": "ProcuradorAnuncios/1.0 (Windows)"},
                timeout=12,
            )
            response.raise_for_status()
            data = response.json()
            coords = [float(data[0]["lat"]), float(data[0]["lon"])] if data else None
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            return None

        cache[key] = coords
        save_cache(cache)
        # O Nominatim pede para manter uma pausa entre pesquisas sem cache.
        time.sleep(1)
        return tuple(coords) if coords else None


def _within_radius(place: str | None, center: str | None, radius: int | None) -> bool:
    """Filtra pela distância em linha reta; dados geográficos ausentes passam."""
    if not place or not center or not radius:
        return True
    a, b = _geocode(place), _geocode(center)
    if not a or not b:
        return True
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    # Limita o valor para evitar erro de arredondamento na raiz quadrada.
    h = min(1.0, max(0.0, h))
    distance_km = 6371 * 2 * atan2(sqrt(h), sqrt(1 - h))
    return distance_km <= float(radius)


def check_olx(search: dict[str, Any]) -> list[dict[str, str]]:
    """Pesquisa a página pública da OLX e devolve anúncios normalizados.

    O seletor CSS da OLX pode mudar. Se houver uma falha HTTP ou a página deixar
    de conter cartões conhecidos, a função levanta um erro que aparece no painel.
    """
    keyword = search["keyword"]
    params = {}
    if search.get("max_price") is not None:
        params["search[filter_float_price:to]"] = search["max_price"]
    if search.get("min_price") is not None:
        params["search[filter_float_price:from]"] = search["min_price"]
    url = f"https://www.olx.pt/ads/q-{requests.utils.quote(keyword)}/"
    try:
        if "OptanonConsent" not in olx_session.cookies.get_dict():
            olx_session.get("https://www.olx.pt/", timeout=20)
            time.sleep(1)
        r = olx_session.get(url, params=params, timeout=20)
        r.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            raise RuntimeError(
                "A OLX recusou esta consulta automática (HTTP 403). Uma atualização "
                "da aplicação não garante a remoção do bloqueio."
            ) from exc
        raise RuntimeError(f"OLX: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"OLX: {exc}") from exc
    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select('[data-cy="l-card"]')
    if not cards:
        cards = soup.select('div[data-testid="listing-grid"] > div')
    if not cards:
        raise RuntimeError("A OLX mudou a página de pesquisa ou não devolveu anúncios.")
    found = []
    pattern = re.compile(re.escape(keyword), re.I)
    for card in cards:
        link_tag = card.select_one("a[href]")
        if not link_tag:
            continue
        link = link_tag.get("href", "")
        if link.startswith("/"):
            link = "https://www.olx.pt" + link
        title_tag = card.select_one('[data-cy="ad-card-title"]') or card.select_one("h4") or card.select_one("h6")
        if title_tag:
            title = title_tag.get_text(" ", strip=True)
        else:
            title = link_tag.get("title") or link_tag.get_text(" ", strip=True)
        price_tag = card.select_one('[data-testid="ad-price"]')
        price = price_tag.get_text(" ", strip=True) if price_tag else "Preço não indicado"
        loc = card.select_one('[data-testid="location-date"]')
        place = loc.get_text(" ", strip=True).split(" - ")[0] if loc else None
        passes_keyword = bool(title and pattern.search(title))
        passes_exclusions = _excluded(title, search.get("exclude_keywords"))
        passes_price = _price_ok(price, search.get("min_price"), search.get("max_price"))
        passes_distance = _within_radius(
            place,
            search.get("center_location"),
            search.get("radius_km"),
        )
        if passes_keyword and passes_exclusions and passes_price and passes_distance:
            found.append({"title": title[:200], "price": price, "link": link})
    return found


def check_wallapop_search(search: dict[str, Any]) -> list[dict[str, str]]:
    """Adapta a resposta da biblioteca Wallapop ao formato interno comum."""
    if check_wallapop is None:
        raise RuntimeError("O conector Wallapop não está instalado nesta versão.")
    items = check_wallapop(
        product_name=search["keyword"],
        keywords=[search["keyword"]],
        min_price=search.get("min_price"),
        max_price=search.get("max_price"),
        max_total_items=40,
        order_by="newest",
    )
    pattern = re.compile(re.escape(search["keyword"]), re.I)
    results = []
    for item in items or []:
        title = item.get("title", "")
        if not pattern.search(title) or not _excluded(title, search.get("exclude_keywords")):
            continue
        price = f"{item.get('price', '?')} {item.get('currency', '')}".strip()
        results.append({"title": title, "price": price, "link": item.get("link", "")})
    return results


def _send_discord(webhook: str, search: dict[str, Any], item: dict[str, str]) -> None:
    """Envia um anúncio num embed do Discord; erros HTTP são devolvidos ao ciclo."""
    if not webhook:
        raise ValueError("Webhook do Discord não configurado.")
    payload = {
        "embeds": [
            {
                "title": item["title"][:250],
                "url": item["link"],
                "description": f"**{item['price']}**\n{search['site'].upper()} · {search['name']}",
                "color": 5793266,
            }
        ]
    }
    response = requests.post(webhook, json=payload, timeout=15)
    response.raise_for_status()


def _remember_seen_link(search_id: str, link: str) -> bool:
    """Persiste um link só depois de o Discord aceitar a notificação."""
    def add_link(search: dict[str, Any]) -> None:
        links = search.get("seen_links", [])
        if not isinstance(links, list):
            links = []
        if link not in links:
            links.append(link)
        search["seen_links"] = links[-500:]

    return update_search(search_id, add_link)


def _remember_check_time(search_id: str) -> None:
    """Guarda a hora da ronda sem substituir alterações recentes da interface."""
    checked_at = datetime.now().isoformat(timespec="minutes")

    def set_check_time(search: dict[str, Any]) -> None:
        search["last_checked"] = checked_at

    update_search(search_id, set_check_time)


def _run_check_once() -> dict[str, Any]:
    """Executa uma ronda de pesquisa e guarda estado e ligações já notificadas."""
    cfg = load_config()
    errors, added = [], 0
    if cfg.get("master_enabled") and not cfg.get("discord_webhook"):
        with status_lock:
            status.update(
                running=False,
                message="Adiciona o webhook do Discord para começar a receber alertas.",
                errors=[],
                new_count=0,
            )
        return dict(status)
    if cfg.get("master_enabled"):
        for search in cfg.get("searches", []):
            if not search.get("enabled", True):
                continue
            try:
                if search.get("site") == "olx":
                    found = check_olx(search)
                elif search.get("site") == "wallapop":
                    found = check_wallapop_search(search)
                else:
                    raise ValueError(f"Site não suportado: {search.get('site')}")

                current = load_config()
                active = next(
                    (item for item in current["searches"] if item.get("id") == search.get("id")),
                    None,
                )
                if active is None:
                    continue
                seen = set(active.get("seen_links", []))
                for item in found:
                    if item["link"] and item["link"] not in seen:
                        _send_discord(current.get("discord_webhook", ""), search, item)
                        if _remember_seen_link(search["id"], item["link"]):
                            seen.add(item["link"])
                            added += 1
                _remember_check_time(search["id"])
            except Exception as exc:
                errors.append(f"{search.get('name', 'Pesquisa')}: {str(exc)[:180]}")
    with status_lock:
        if errors:
            message = "Verificação concluída com avisos."
        else:
            message = f"Verificação concluída · {added} anúncio(s) novo(s)."
        status.update(
            last_run=datetime.now().isoformat(timespec="seconds"),
            running=False,
            new_count=added,
            errors=errors,
            message=message,
        )
    return dict(status)


def check_once() -> dict[str, Any]:
    """Executa no máximo uma ronda de cada vez, mesmo com cliques manuais.

    Sem esta exclusão, o ciclo automático e o botão «Verificar agora» podiam
    descobrir o mesmo anúncio em simultâneo e enviar notificações duplicadas.
    """
    if not check_lock.acquire(blocking=False):
        with status_lock:
            return dict(status)
    try:
        return _run_check_once()
    finally:
        check_lock.release()


def monitor_loop() -> None:
    """Ciclo de fundo: verifica pesquisas e espera o intervalo configurado."""
    while True:
        with status_lock:
            status["running"] = True
        check_once()
        cfg = load_config()
        time.sleep(max(60, min(int(cfg.get("interval_seconds", 300)), 86400)))


def start_monitor() -> None:
    """Inicia um único thread de monitorização para o processo atual."""
    global monitor_thread
    with monitor_start_lock:
        if monitor_thread and monitor_thread.is_alive():
            return
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="monitor-anuncios")
        monitor_thread.start()
