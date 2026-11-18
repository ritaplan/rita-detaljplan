"""Pluginets inställningar (sparas i QGIS användarprofil)."""
from __future__ import annotations

import re
from typing import Optional

from qgis.core import QgsApplication, QgsSettings

# Obs: nycklarna nedan behåller det gamla prefixet ``detaljplan_ngp`` (pluginet hette förr Detaljplan NGP) så att redan
# skapade projekt och sparade inställningar fortsätter fungera efter namnbytet.
KEY_REFERENCE_SCALE = "detaljplan_ngp/reference_scale"
DEFAULT_REFERENCE_SCALE = 1000
SCALES = (200, 500, 1000, 2000, 4000, 5000, 10000)  # förslag i inställningsdialogen
MIN_SCALE, MAX_SCALE = 100, 50000


KEY_NGP = "detaljplan_ngp/ngp/"
KEY_SHOW_INTERPRETATION = "detaljplan_ngp/show_interpretation"


def show_interpretation() -> bool:
    """Om tolkningsbestämmelserna (för äldre planer) ska visas direkt i listan när bestämmelser tilldelas."""
    return str(QgsSettings().value(KEY_SHOW_INTERPRETATION, "false")).lower() in ("true", "1")


def set_show_interpretation(value: bool) -> None:
    QgsSettings().setValue(KEY_SHOW_INTERPRETATION, bool(value))


def _environment_name(value) -> str:
    """Miljön som ett av de kända namnen ("ver", "prod"), annars "egen" (en tidigare inställning med egen adress)."""
    from . import ngp_client as ngp
    text = str(value)
    return text if text in ngp.ENVIRONMENTS else "egen"


def active_ngp_environment() -> str:
    """Miljön leveransen går till ("ver", "prod" eller "egen")."""
    return _environment_name(QgsSettings().value(KEY_NGP + "environment", "ver"))


def ngp_environment_config(environment: str):
    """Adresser och nyckel för en miljö. Varje miljö har egna inställningar. Inställningar som sparats före uppdelningen
    (en enda uppsättning för den miljö som var vald) gäller fortfarande för den miljön tills man sparar på nytt."""
    from . import ngp_client as ngp
    store = QgsSettings()
    defaults = ngp.ENVIRONMENTS.get(environment)
    legacy_here = active_ngp_environment() == environment

    def read(name: str, default: str = "") -> str:
        value = store.value(f"{KEY_NGP}{environment}/{name}")
        if value is None and legacy_here:
            value = store.value(KEY_NGP + name)
        return default if value is None else str(value or "")

    return ngp.NgpConfig(environment=environment,
                         base_url=read("base_url", defaults.base_url if defaults else ""),
                         token_url=read("token_url", defaults.token_url if defaults else ""),
                         authcfg=read("authcfg"))


def ngp_config():
    """Inställningarna för leverans till NGP: den miljö leveransen går till, med dess adresser och autentiseringskonfiguration."""
    return ngp_environment_config(active_ngp_environment())


def set_ngp_config(config) -> None:
    """Sparar inställningarna för en miljö (config.environment). Miljön som leveransen går till ändras med ``set_ngp_active``."""
    store = QgsSettings()
    prefix = f"{KEY_NGP}{config.environment}/"
    store.setValue(prefix + "base_url", config.base_url.strip())
    store.setValue(prefix + "token_url", config.token_url.strip())
    store.setValue(prefix + "authcfg", config.authcfg)
    if QgsSettings().value(KEY_NGP + "environment") is None:  # första sparningen: den miljön blir den aktiva
        store.setValue(KEY_NGP + "environment", config.environment)


def set_ngp_active(environment: str) -> None:
    QgsSettings().setValue(KEY_NGP + "environment", environment)


def ngp_search_config():
    """Inställningarna för att fråga NGP om en plan finns där (Sök-API:et): miljön (som standard den leveransen går till),
    dess adresser, och nyckeln för sökningen (``search_authcfg``; tom = leveransnyckeln för miljön)."""
    from dataclasses import replace
    store = QgsSettings()
    environment = _environment_name(store.value(KEY_NGP + "search/environment", active_ngp_environment()))
    key = store.value(KEY_NGP + "search/authcfg")
    if key is None:  # sparad före uppdelningen
        key = store.value(KEY_NGP + "search_authcfg", "")
    return replace(ngp_environment_config(environment), search_authcfg=str(key or ""))


def set_ngp_search(environment: str, authcfg: str) -> None:
    store = QgsSettings()
    store.setValue(KEY_NGP + "search/environment", environment)
    store.setValue(KEY_NGP + "search/authcfg", authcfg)


def auth_configs() -> list[tuple[str, str]]:
    """QGIS autentiseringskonfigurationer som (id, namn). Tom lista om autentiseringsdatabasen inte kan läsas."""
    try:
        configs = QgsApplication.authManager().availableAuthMethodConfigs()
        return sorted(((cid, cfg.name()) for cid, cfg in configs.items()), key=lambda item: item[1].lower())
    except Exception:  # noqa: BLE001 - t.ex. låst databas eller saknad huvudlösenordsfråga
        return []


def scale_text(scale: int) -> str:
    return f"1:{scale}"


def parse_scale(text: str) -> Optional[int]:
    """Läser "1:1000" eller "1000" som 1000. None om texten inte är en skala."""
    match = re.fullmatch(r"\s*(?:1\s*:\s*)?(\d{2,6})\s*", text or "")
    return int(match.group(1)) if match else None


def clamp_scale(value) -> int:
    try:
        scale = int(round(float(value)))
    except (TypeError, ValueError):
        return DEFAULT_REFERENCE_SCALE
    return max(MIN_SCALE, min(MAX_SCALE, scale))


def reference_scale() -> int:
    """Referensskalan (nämnaren, 1000 = 1:1000) som linjer och texter dimensioneras för."""
    return clamp_scale(QgsSettings().value(KEY_REFERENCE_SCALE, DEFAULT_REFERENCE_SCALE))


def set_reference_scale(value) -> int:
    scale = clamp_scale(value)
    QgsSettings().setValue(KEY_REFERENCE_SCALE, scale)
    return scale
