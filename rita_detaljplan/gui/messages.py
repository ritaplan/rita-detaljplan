"""Meddelanden i QGIS meddelandefält (överkanten av kartfönstret): alla stängs av sig själva efter några sekunder."""
from qgis.core import Qgis

from .richtext import esc

DURATION = {
    Qgis.MessageLevel.Info: 5,
    Qgis.MessageLevel.Success: 5,
    Qgis.MessageLevel.Warning: 10,
    Qgis.MessageLevel.Critical: 10,
}


def push(bar, title: str, text: str, level=Qgis.MessageLevel.Info) -> None:
    if "<" in text or "&" in text:  # meddelandefältet tolkar HTML: text ur databasen eller en fil ska visas som den är
        text = esc(text).replace("\n", "<br>")
    bar.pushMessage(title, text, level=level, duration=DURATION.get(level, 10))
