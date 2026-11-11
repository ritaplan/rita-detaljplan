"""Skrivskydd för en plan i databasen: en plan som inte får ändras, till exempel en detaljplan som har vunnit laga kraft.

Skrivskyddet är en rad ``skrivskydd`` i planens metadata (``dp_meta``) med JSON: vem som skyddade planen, på vilken dator,
när och (valfritt) varför. Det är något annat än utcheckningens lås: ett lås tillhör den som redigerar planen just nu och
släpps när den checkas in, medan skrivskyddet ligger kvar tills någon bryter det med avsikt.

Så länge planen är skrivskyddad kan den öppnas, exporteras och kopieras (kopian är en ny, oskyddad plan), men den kan inte
checkas ut och inte tas bort. Att skydda eller bryta skyddet görs i databashanteraren (se ``core.checkout``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

PROTECT_KEY = "skrivskydd"


@dataclass(frozen=True)
class Protection:
    user: str
    host: str
    since: str
    reason: str = ""

    def describe(self) -> str:
        """Vem och när, och skälet om det finns: ``anna på DATOR-1 sedan 2026-11-11 10:15: laga kraft``."""
        text = f"{self.user} på {self.host} sedan {self.since.replace('T', ' ')}"
        return f"{text}: {self.reason}" if self.reason else text

    def to_json(self) -> str:
        return json.dumps({"user": self.user, "host": self.host, "since": self.since, "reason": self.reason})

    @classmethod
    def from_json(cls, text: str) -> Optional["Protection"]:
        try:
            data = json.loads(text)
            return cls(str(data.get("user", "")), str(data.get("host", "")), str(data.get("since", "")),
                       str(data.get("reason", "")))
        except (ValueError, TypeError, AttributeError):
            return None
