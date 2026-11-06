"""Översikt över planerna i en PostGIS-databas: en rad per plan med de uppgifter man vill se innan man öppnar den.

Allt hämtas med några få frågor per schema (inte en per plan), så överblicken går snabbt även över nätet. Planens
geometri läses aldrig här. Saknas en tabell eller kolumn (ett äldre schema) lämnas fälten tomma i stället för att
överblicken misslyckas: bara listan över planer måste gå att läsa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import checkout, model, storage
from .storage import PostgisError, literal, quote

BESLUT_TABLE = "beslutsinformation"


@dataclass(frozen=True)
class PlanRow:
    connection: str
    schema: str
    plan_id: str
    namn: str = ""
    beteckning: str = ""
    kommun: str = ""
    syfte: str = ""
    status: str = ""
    typ: str = ""
    status_datum: str = ""
    diarienummer: str = ""
    paborjad: str = ""
    antagande: str = ""
    laga_kraft: str = ""
    genomforandetid: str = ""
    lock: Optional[checkout.Lock] = None

    @property
    def locked(self) -> bool:
        return self.lock is not None

    @property
    def locked_by_me(self) -> bool:
        """Utcheckad av den här användaren på den här datorn (då kan utcheckningen tas upp igen)."""
        return self.lock is not None and checkout.is_own_lock(self.lock)


def _text(value) -> str:
    """Ett databasvärde som visningstext. NULL och None blir tom text, datum blir ÅÅÅÅ-MM-DD."""
    if value is None:
        return ""
    to_string = getattr(value, "toString", None)
    if callable(to_string):  # QDate / QDateTime
        if getattr(value, "isNull", lambda: False)():
            return ""
        return str(to_string("yyyy-MM-dd"))
    text = str(value).strip()
    return "" if text in ("NULL", "None") else text[:10] if _looks_like_datetime(text) else text


def _looks_like_datetime(text: str) -> bool:
    return len(text) > 10 and text[4:5] == "-" and text[7:8] == "-" and text[:4].isdigit() and text[10] in " T"


def _query(connection, sql: str) -> list:
    """En fråga där ett fel inte får stoppa överblicken (saknad tabell eller kolumn i ett äldre schema)."""
    try:
        return storage._execute(connection, sql)
    except PostgisError:
        return []


def _locks(connection, schema: str) -> dict[str, checkout.Lock]:
    rows = _query(connection, f'SELECT "plan", "value" FROM {quote(schema)}.{quote(model.META_TABLE)} '
                              f'WHERE "key" = {literal(checkout.LOCK_KEY)}')
    locks = {}
    for row in rows:
        lock = checkout.Lock.from_json(_text(row[1]))
        if lock is not None:
            locks[_text(row[0])] = lock
    return locks


def _plan_fields(connection, schema: str) -> dict[str, dict[str, str]]:
    rows = _query(connection, 'SELECT "plan", "namn", "beteckning", "kommun", "syfte", "status", "typ", '
                              f'"datumStatusforandring" FROM {quote(schema)}.{quote(model.DETALJPLAN.name)}')
    keys = ("namn", "beteckning", "kommun", "syfte", "status", "typ", "status_datum")
    return {_text(row[0]): dict(zip(keys, (_text(v) for v in row[1:]))) for row in rows}


def _decision_fields(connection, schema: str) -> dict[str, dict[str, str]]:
    """Beslutsinformation har en rad per beslut: ta fram en sammanfattning per plan (tidigaste påbörjandet,
    senaste antagandet och laga kraft-datumet)."""
    rows = _query(connection, 'SELECT "plan", "diarienummerKommun", "datumPaborjat", "datumAntagande", '
                              '"datumLagakraft", "genomforandetid" FROM '
                              f'{quote(schema)}.{quote(BESLUT_TABLE)} ORDER BY "plan"')
    grouped: dict[str, list[list[str]]] = {}
    for row in rows:
        grouped.setdefault(_text(row[0]), []).append([_text(v) for v in row[1:]])
    result = {}
    for plan_id, items in grouped.items():
        def first(index):
            return next((item[index] for item in items if item[index]), "")

        def dates(index):
            return [d.strip() for item in items for d in item[index].split(";") if d.strip()]
        result[plan_id] = {
            "diarienummer": first(0),
            "paborjad": min(dates(1), default=""),
            "antagande": max(dates(2), default=""),
            "laga_kraft": max(dates(3), default=""),
            "genomforandetid": first(4),
        }
    return result


def list_plans(connection_name: str, connection, schema: str) -> list[PlanRow]:
    """Alla planer i ett schema, med planens uppgifter och ev. utcheckning. Kastar ``PostgisError`` om det inte
    går att ens lista planerna."""
    plan_ids = storage.list_plans_in_schema(connection, schema)
    locks = _locks(connection, schema)
    fields = _plan_fields(connection, schema)
    decisions = _decision_fields(connection, schema)
    return [PlanRow(connection_name, schema, plan_id, lock=locks.get(plan_id),
                    **{**fields.get(plan_id, {}), **decisions.get(plan_id, {})})
            for plan_id in plan_ids]
