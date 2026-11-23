"""Tilldelade bestämmelser (tabellen ``bestammelse``): en rad per bestämmelse och yta.

En yta kan ha flera bestämmelser (kombinerad användning, flera egenskaper). Beteckningen på plankartan är
sammansatt av ytans bestämmelser: användning skrivs ihop ("B" + "C" = "BC"), egenskaper med mellanrum ("e1 a2").
Indexerade beteckningar ("R#", "e#") numreras per bokstav i hela planen: samma bestämmelse (samma text och
värden) får samma beteckning överallt, en annan får nästa lediga nummer.

Raderna är vanliga dictar med kolumnerna i ``model.BESTAMMELSE``. Modulen är ren Python (inget QGIS).
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from . import bestammelse as bm
from . import catalog as cat
from . import vertical

# Attribut som beskriver en bestämmelse (kommer från ``bestammelse.feature_attributes``).
ATTRIBUTE_KEYS = ("planbestammelsekatalogreferens", "bestammelsekod", "anvandningsform", "farg", "symbol",
                  "bestammelseformulering", "avviker", "ursprungligBestammelseformulering", "bestammelsevarde",
                  "motiv")


def chosen_label(entry: cat.CatalogEntry, text: Optional[str]) -> str:
    """Det planförfattaren skrivit som beteckning, så som det används. Är katalogens beteckning indexerad ("#")
    läggs siffran på automatiskt, så siffror i slutet av det som skrivs ("dagvatten1") tas bort: annars kunde två olika
    bestämmelser få likadana beteckningar eller en siffra för mycket ("dagvatten11")."""
    chosen = (text or "").replace("#", "").strip()
    if "#" in entry.beteckning:
        chosen = chosen.rstrip("0123456789").rstrip()
    return chosen


def _label_template(entry: cat.CatalogEntry, text: Optional[str]) -> str:
    """Katalogens beteckning med variabeln ersatt av planförfattarens text ("[beteckning:text]#" + "Dv" -> "Dv#")."""
    template = entry.beteckning
    chosen = chosen_label(entry, text)
    for variable in entry.label_variables:
        template = template.replace(variable.token, chosen)
    return template


def label_for(entry: cat.CatalogEntry, index: Optional[int], text: Optional[str] = None) -> str:
    """Beteckning på plankartan: "e#" med index 2 blir "e2"; utan "#" används beteckningen som den är. Har katalogens
    beteckning en variabel ("[beteckning:text]#") fyller ``text`` i den: "Dv" med index 1 blir "Dv1"."""
    template = _label_template(entry, text)
    if "#" in template and index is not None:
        return template.replace("#", str(index))
    return template.strip()


HEIGHT_SYMBOL = "Höjd över nollplanet"  # katalogens symbol för markens höjd över (eller under) nollplanet i en punkt


SLOPE_SYMBOL = "Största/minsta lutning"  # katalogens symbol för största och minsta lutning (en pil med lutningsförhållandet)


def slope_label(entry: cat.CatalogEntry, values: Iterable[bm.VariableValue]) -> Optional[str]:
    """Beteckningen för största eller minsta lutning, som på plankartan: lutningsförhållandet med decimalkomma ("1:20",
    "1:2,5"). Katalogen har ingen beteckning för de bestämmelserna, det är värdet som visas, och det ritas ovanför pilen
    (BFS 2020:6, 7.2 och 7.13). None för andra bestämmelser, eller om värdena inte är ifyllda."""
    if entry.symbol != SLOPE_SYMBOL:
        return None
    numbers = [bm.normalize_decimal(v.value) for v in values if v.variable.datatype == "decimaltal"]
    if len(numbers) < 2 or not all(numbers[:2]):
        return None
    return ":".join(number.replace(".", ",") for number in numbers[:2])


def height_label(entry: cat.CatalogEntry, values: Iterable[bm.VariableValue]) -> Optional[str]:
    """Beteckningen för markens höjd i en punkt, som på plankartan: höjden med tecken och decimalkomma ("+31,8"; under
    nollplanet "-2,5"). Katalogen har ingen beteckning för de bestämmelserna, det är värdet som visas. None för andra
    bestämmelser, eller om höjden inte är ifylld."""
    if entry.symbol != HEIGHT_SYMBOL:
        return None
    number = next((bm.normalize_decimal(v.value) for v in values
                   if v.variable.datatype == "decimaltal" and bm.normalize_decimal(v.value)), None)
    if number is None:
        return None
    sign = "-" if "under nollplanet" in entry.formulering else "+"
    return sign + number.lstrip("-").replace(".", ",")


def label_problems(entry: cat.CatalogEntry, text: Optional[str]) -> list[str]:
    """Felmeddelanden om beteckningen: har katalogen en variabel i beteckningen ska planförfattaren ange den."""
    if entry.label_variables and not chosen_label(entry, text):
        if "#" in entry.beteckning:
            return ["Ange bokstäver till beteckningen som ska visas på plankartan. Siffran läggs på automatiskt."]
        return ["Ange beteckningen som ska visas på plankartan."]
    return []


def label_text(entry: cat.CatalogEntry, row: dict) -> Optional[str]:
    """Det planförfattaren skrev som beteckning för en rad (t.ex. "Dv" i "Dv1"), eller None om katalogens beteckning
    inte har någon variabel."""
    if not entry.label_variables:
        return None
    text = base(row.get("beteckning"), row.get("beteckningsindex"))
    return "" if cat.parse_variables(text) else text  # en äldre rad kan ha mallen sparad som beteckning


def identity(row: dict) -> tuple:
    """Det som gör två bestämmelser till samma bestämmelse i planen (motivet räknas inte)."""
    return (row.get("planbestammelsekatalogreferens"), row.get("bestammelseformulering"),
            row.get("bestammelsevarde") or None)


def base(label: Optional[str], index: Optional[int]) -> str:
    """Beteckningens bokstav ("R2" med index 2 -> "R")."""
    text = (label or "").strip()
    suffix = str(index) if index is not None else ""
    return text[: -len(suffix)] if suffix and text.endswith(suffix) else text


def next_index(rows: Iterable[dict], entry: cat.CatalogEntry, text: Optional[str] = None) -> int:
    """Lägsta lediga index bland raderna med samma beteckningsbokstav (``text``: planförfattarens beteckning)."""
    wanted = label_for(entry, None, text).replace("#", "").strip()
    used = {row.get("beteckningsindex") for row in rows
            if row.get("beteckningsindex") is not None
            and base(row.get("beteckning"), row.get("beteckningsindex")) == wanted}
    index = 1
    while index in used:
        index += 1
    return index


def build_row(entry: cat.CatalogEntry, values: list[bm.VariableValue], motiv: Optional[str] = None,
              formulation: Optional[str] = None, existing_rows: Iterable[dict] = (),
              label: Optional[str] = None) -> dict[str, Any]:
    """Skapar en bestämmelserad. ``existing_rows`` = alla rader i planen, för numreringen av beteckningen. ``label``
    är beteckningen planförfattaren valt när katalogens beteckning har en variabel ("[beteckning:text]#")."""
    if not entry.deliverable:
        raise ValueError(f"{entry.kod or entry.formulering} kan inte användas i en detaljplan (typ {entry.typ}).")
    rows = list(existing_rows)
    attributes = bm.feature_attributes(entry, values, motiv, formulation)
    index: Optional[int] = None
    if "#" in entry.beteckning:
        wanted = label_for(entry, None, label).replace("#", "").strip()
        same = next((r for r in rows if identity(r) == identity(attributes) and r.get("beteckningsindex") is not None
                     and base(r.get("beteckning"), r.get("beteckningsindex")) == wanted), None)
        index = same["beteckningsindex"] if same else next_index(rows, entry, label)
    return {**attributes, "tabell": entry.layer_name,
            "beteckning": label_for(entry, index, label) or height_label(entry, values) or slope_label(entry, values) or None,
            "beteckningsindex": index}


SYMBOL_SEPARATOR = "|"  # ytans symbol är alla bestämmelsernas symboler, åtskilda av detta tecken


def summarize(rows: Iterable[dict]) -> dict[str, Any]:
    """Det en yta visar utifrån sina bestämmelser: beteckning, färg, symboler och användningsform.

    Saknas bestämmelser är ``bestammelser`` 0 och beteckningen tom (NULL), och ytan ritas som "saknar bestämmelse"."""
    rows = list(rows)
    if not rows:
        return {"beteckning": None, "farg": None, "symbol": None, "anvandningsform": None, "bestammelser": 0}
    labels: list[str] = []
    for row in rows:
        label = (row.get("beteckning") or "").strip()
        if label and label not in labels:
            labels.append(label)
    symbols: list[str] = []  # alla symboler, i bestämmelsernas ordning: en yta kan ha både korsmark och fastighetsindelning
    for row in rows:
        symbol = row.get("symbol")
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    use = rows[0].get("tabell") == cat.USE_LAYER
    return {
        "beteckning": ("" if use else " ").join(labels),
        "farg": next((r["farg"] for r in rows if r.get("farg")), None),
        "symbol": SYMBOL_SEPARATOR.join(symbols) or None,
        "anvandningsform": next((r["anvandningsform"] for r in rows if r.get("anvandningsform")), None),
        "bestammelser": len(rows),
    }


def display_text(row: dict) -> str:
    """Formuleringen med värdena ifyllda, ur en lagrad rad."""
    text = row.get("bestammelseformulering") or ""
    try:
        stored = json.loads(row.get("bestammelsevarde") or "[]")
    except json.JSONDecodeError:
        stored = []
    by_name = {item.get("beskrivning"): item.get("variabelvarde", "") for item in stored if isinstance(item, dict)}
    filled = {var.token: by_name[var.name] for var in cat.parse_variables(text) if var.name in by_name}
    return cat.render(text, filled)


def display_text_with_units(row: dict) -> str:
    """Som ``display_text``, men med den valda enheten efter tal som katalogens text inte själv ger någon enhet för, i
    klartext för den som läser en teckenförklaring eller en lista: "Största lutning är 4:5 (meter). (Pilen pekar uppåt)".
    Enheten finns i bestämmelsens värden och levereras, men inte i formuleringen, som måste vara katalogens exakta text
    (DP-0022), så den här texten används bara för visning. De flesta formuleringar har enheten i texten ("… 12 meter"):
    de blir oförändrade. Ett förhållande (a:b) med samma enhet på båda talen får enheten en gång, efter det sista talet.
    Enheten "antal" visas inte."""
    text = row.get("bestammelseformulering") or ""
    try:
        stored = json.loads(row.get("bestammelsevarde") or "[]")
    except json.JSONDecodeError:
        stored = []
    by_name = {item.get("beskrivning"): item for item in stored if isinstance(item, dict)}
    variables = cat.parse_variables(text)
    positions, cursor = [], 0
    for var in variables:
        start = text.find(var.token, cursor)
        positions.append((start, start + len(var.token)))
        cursor = start + len(var.token)
    units = []  # enheten att visa efter varje variabel, eller None
    for var in variables:
        item = by_name.get(var.name) or {}
        unit = item.get("enhet") if item.get("datatyp") == "decimaltal" else None
        units.append(unit if unit and unit != "antal" and cat.guess_unit(text, var) is None else None)
    for i in range(len(variables) - 1):  # ett förhållande (a:b) med samma enhet: bara efter det sista talet
        if units[i] and units[i] == units[i + 1] and text[positions[i][1]:positions[i + 1][0]] == ":":
            units[i] = None
    filled = {}
    for var, unit in zip(variables, units):
        item = by_name.get(var.name)
        if item is not None:
            value = str(item.get("variabelvarde", ""))
            filled[var.token] = f"{value} ({unit})" if unit and value else value
    return cat.render(text, filled)


def describe(row: dict) -> str:
    """Kort text till listor: "R1 – Motorsportbana". Har bestämmelsen en höjd står den sist: "G – Garage (−6,0 till 0,0 m)"."""
    label = (row.get("beteckning") or "").strip()
    text = display_text_with_units(row)
    extent = vertical.extent_of(row)
    if extent.limited:
        text += f" ({extent.text()})"
    return f"{label} – {text}" if label else text
