"""
olx_checker.py — lógica de verificação da OLX (isolada de propósito)
======================================================================
Este ficheiro é a parte "volátil" do Monitor de Anúncios: sempre que a
OLX mudar a estrutura do site, é só este ficheiro que precisa de ser
corrigido e republicado no GitHub. A aplicação principal (app.py)
descarrega automaticamente a versão mais recente deste ficheiro sempre
que abre, e usa-a em vez desta cópia embutida no .exe.

Sobe sempre o número em __version__ quando publicares uma correção —
é assim que a aplicação sabe que há uma versão nova.
"""

__version__ = "1.0.0"

import re
import time
from math import radians, sin, cos, sqrt, atan2

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Geocodificação (para o filtro "no máximo X km de ...")
# ---------------------------------------------------------------------------

def geocode(place_name, cache):
    """Converte um nome de local em (latitude, longitude), via Nominatim
    (OpenStreetMap, gratuito). 'cache' é um dict fornecido pelo chamador
    (persistido em disco por quem usa este módulo)."""
    if not place_name:
        return None
    key = place_name.strip().lower()
    if key in cache:
        return tuple(cache[key]) if cache[key] else None
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place_name, "format": "json", "limit": 1, "countrycodes": "pt"},
            headers={"User-Agent": "monitor-anuncios-pessoal/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        coords = (float(data[0]["lat"]), float(data[0]["lon"])) if data else None
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        print(f"[aviso] geocodificação falhou para '{place_name}': {e}")
        coords = None
    cache[key] = list(coords) if coords else None
    time.sleep(1)  # limite do Nominatim: 1 pedido/segundo
    return coords


def haversine_km(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    r = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def within_radius(ad_location_text, center_location, radius_km, geocode_cache):
    if not center_location or not radius_km or not ad_location_text:
        return True
    center_coords = geocode(center_location, geocode_cache)
    ad_coords = geocode(ad_location_text, geocode_cache)
    if not center_coords or not ad_coords:
        return True
    return haversine_km(center_coords, ad_coords) <= float(radius_km)


def passes_exclude_filter(title, exclude_keywords):
    if not exclude_keywords:
        return True
    title_lower = title.lower()
    return not any(w.strip().lower() in title_lower for w in exclude_keywords if w.strip())


def _price_in_range(price_str, min_price, max_price):
    if not min_price and not max_price:
        return True
    if not price_str:
        return True
    digits = re.sub(r"[^\d]", "", str(price_str))
    if not digits:
        return True
    value = int(digits)
    if min_price and value < int(min_price):
        return False
    if max_price and value > int(max_price):
        return False
    return True


# ---------------------------------------------------------------------------
# OLX — leitura da página de pesquisa, com múltiplas estratégias de extração
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Referer": "https://www.olx.pt/",
}

_olx_session = requests.Session()
_olx_session.headers.update(HEADERS)

_KNOWN_CARD_SELECTORS = [
    '[data-cy="l-card"]',
    'div[data-testid="listing-grid"] > div',
    'div[data-testid="l-card"]',
]
_KNOWN_TITLE_SELECTORS = ['[data-cy="ad-card-title"]', 'h4', 'h6']
_KNOWN_PRICE_SELECTORS = ['[data-testid="ad-price"]', '[data-cy="ad-price"]']
_KNOWN_LOCATION_SELECTORS = ['[data-testid="location-date"]']

_PRICE_TEXT_PATTERN = re.compile(r'(\d[\d.\s]{0,9}(?:,\d{2})?)\s*€')
_AD_LINK_PATTERN = re.compile(r'/d/|-ID[a-zA-Z0-9]+\.html')


def _parse_known_card(card):
    link_tag = card.select_one("a[href]")
    if not link_tag:
        return None
    link = link_tag["href"]
    if link.startswith("/"):
        link = "https://www.olx.pt" + link

    title = None
    for sel in _KNOWN_TITLE_SELECTORS:
        tag = card.select_one(sel)
        if tag and tag.get_text(strip=True):
            title = tag.get_text(strip=True)
            break
    if not title:
        title = link_tag.get("title") or link_tag.get_text(strip=True)
    if not title:
        return None

    price_str = None
    for sel in _KNOWN_PRICE_SELECTORS:
        tag = card.select_one(sel)
        if tag and tag.get_text(strip=True):
            price_str = tag.get_text(strip=True)
            break

    location_text = None
    for sel in _KNOWN_LOCATION_SELECTORS:
        tag = card.select_one(sel)
        if tag and tag.get_text(strip=True):
            location_text = tag.get_text(strip=True).split(" - ")[0].strip()
            break

    return {"title": title[:200], "link": link, "price": price_str, "location": location_text}


def _parse_ads_heuristic(soup):
    ads = []
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _AD_LINK_PATTERN.search(href):
            continue
        link = href if href.startswith("http") else "https://www.olx.pt" + href
        if link in seen_links:
            continue

        title = a.get("title") or a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        seen_links.add(link)

        container = a.find_parent(["li", "article", "div"]) or a
        container_text = container.get_text(" ", strip=True)
        price_match = _PRICE_TEXT_PATTERN.search(container_text)
        price_str = f"{price_match.group(1)} €" if price_match else None

        ads.append({"title": title[:200], "link": link, "price": price_str, "location": None})
    return ads


def _extract_ads(soup):
    for selector in _KNOWN_CARD_SELECTORS:
        cards = soup.select(selector)
        if not cards:
            continue
        ads = [a for a in (_parse_known_card(c) for c in cards) if a]
        if ads:
            return ads, "seletores conhecidos"

    ads = _parse_ads_heuristic(soup)
    if ads:
        return ads, "heurística genérica"

    return [], "nenhuma"


def check_olx(keyword, max_price=None, min_price=None, exclude_keywords=None,
              center_location=None, radius_km=None, geocode_cache=None, debug_path=None):
    """Função principal chamada pela aplicação. geocode_cache é um dict
    (persistido pelo chamador); debug_path é onde gravar o HTML quando
    0 anúncios são encontrados, para diagnóstico."""
    if geocode_cache is None:
        geocode_cache = {}

    results = []
    url = f"https://www.olx.pt/ads/q-{requests.utils.quote(keyword)}/"
    params = {}
    if max_price:
        params["search[filter_float_price:to]"] = max_price
    if min_price:
        params["search[filter_float_price:from]"] = min_price

    try:
        if "OptanonConsent" not in _olx_session.cookies.get_dict():
            _olx_session.get("https://www.olx.pt/", timeout=20)
            time.sleep(1)
        resp = _olx_session.get(url, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[erro] OLX: {e}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    ads, strategy = _extract_ads(soup)

    if not ads:
        if debug_path:
            try:
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(resp.text)
            except OSError:
                pass
        print(f"[aviso] OLX: 0 anúncios encontrados para '{keyword}' com nenhuma estratégia")
        return results

    kw_regex = re.compile(re.escape(keyword), re.IGNORECASE)

    for ad in ads:
        if not kw_regex.search(ad["title"]):
            continue
        if not passes_exclude_filter(ad["title"], exclude_keywords):
            continue
        if not _price_in_range(ad["price"], min_price, max_price):
            continue
        if not within_radius(ad["location"], center_location, radius_km, geocode_cache):
            continue
        results.append({"title": ad["title"], "price": ad["price"] or "?", "link": ad["link"]})

    print(f"[info] OLX '{keyword}': {len(ads)} anúncios lidos (estratégia: {strategy}), "
          f"{len(results)} corresponderam aos critérios")
    return results
