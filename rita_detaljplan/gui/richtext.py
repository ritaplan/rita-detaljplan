"""Text utifrån (databasen, en fil, en tjänst, Boverkets katalog) får inte tolkas som Qts rika text (HTML-delmängd): den
kan då ändra hur texten ser ut, och få Qt att läsa in en bildfil som texten pekar på, också över nätverket.

* ``plain``: en etikett eller meddelanderuta som bara visar ren text.
* ``as_text``: för ett ställe där Qt själv gissar formatet, som ett verktygstips.
* ``esc``: för text som sätts in i en dialog som med flit är formaterad."""
from html import escape

from qgis.PyQt.QtCore import Qt


def esc(value) -> str:
    return escape(str(value), quote=False)


def plain(widget):
    """Etiketten eller meddelanderutan visar sin text som den är, också när den ser ut som formaterad text."""
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def as_text(value) -> str:
    """Utan < och & lämnas texten som den är. Annars kodas den och visas bokstavligt."""
    text = str(value)
    if "<" not in text and "&" not in text:
        return text
    return f'<qt><span style="white-space: pre-wrap;">{esc(text)}</span></qt>'
