"""Dialogen "Leverans och export": kontrollera planen och välj att leverera den till NGP, spara den som JSON-fil eller
samla den i ett arkivpaket.

Dialogen öppnas alltid, även om inställningarna för leverans till NGP inte är gjorda: då är uppladdning avstängd med en
förklaring av vad som saknas (och en knapp till inställningarna), medan filalternativet fungerar ändå. Filen kan
skickas till NGP-supporten för granskning eller laddas upp av en producent.

Utseendet: en ruta överst med planens kontroll (med en tydlig markering av resultatet) och sedan ett kort per val, med
ikon, rubrik och förklaring. Kortet som är valt har en färgad ram, och ett klick var som helst på ett kort väljer det."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFrame, QGroupBox, QHBoxLayout, QLabel,
                                 QPushButton, QRadioButton, QVBoxLayout)

from ..controller import PlanController
from ..core.ngp_client import NgpConfig
from .delivery_dialog import confirmation_text
from .plan_switcher import build_plan_switcher
from .richtext import esc

ICONS = Path(__file__).resolve().parent.parent / "icons"
UPLOAD, FILE, ARCHIVE = "upload", "file", "archive"
GOOD, WARNING, ERROR = "good", "warning", "error"  # kontrollens resultat
# tecken och färg för resultatet
MARKS = {GOOD: ("✔", "#1b7f3b"), WARNING: ("▲", "#b06e00"), ERROR: ("✘", "#b3261e")}
# kontrollen är inte ett av alternativen och får inte se ut som ett valt kort (blå ram): en grå ruta med en bred kant i
# resultatets färg (genomskinlig, så att den fungerar i ljust och mörkt tema)
CHECK_BOX_STYLE = """
QGroupBox#checkBox { background-color: rgba(128, 128, 128, 22); border: 1px solid rgba(128, 128, 128, 70);
                     border-left: 5px solid rgba(%s); border-radius: 4px; margin-top: 8px; padding-top: 4px; }
QGroupBox#checkBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px; }
"""
CHECK_COLOURS = {GOOD: "27, 127, 59, 230", WARNING: "214, 140, 0, 230", ERROR: "179, 38, 30, 230"}
# korten för valen: en tunn ram, och en färgad ram med lätt bakgrund på det valda kortet (genomskinligt, för båda teman)
DIALOG_STYLE = """
QFrame#choiceCard { border: 1px solid rgba(128, 128, 128, 100); border-radius: 6px; }
QFrame#choiceCard:hover { border-color: rgba(30, 110, 200, 170); }
QFrame#choiceCard[chosen="true"] { border: 2px solid rgba(30, 110, 200, 220); background-color: rgba(30, 110, 200, 22); }
QFrame#choiceCard[available="false"] { background-color: rgba(128, 128, 128, 18); }
QLabel#muted { color: palette(placeholder-text); }
"""
ICON_SIZE = 28


@dataclass(frozen=True)
class NgpRequest:
    """Vad dialogen behöver veta om planen."""
    plan_name: str = ""
    kommun: str = ""
    kommunkod: str = ""  # tom om planens kommun saknas
    errors: int = 0
    warnings: int = 0
    resuming: bool = False


class ChoiceCard(QFrame):
    """Ett val med ikon, rubrik (radioknappen) och förklaring. Ett klick var som helst på kortet väljer det, och kortet
    får en färgad ram när det är valt. Radioknappen och innehållet läggs i ``body``."""

    def __init__(self, radio: QRadioButton, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("choiceCard")
        self.radio = radio
        self.setProperty("chosen", False)
        self.setProperty("available", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        symbol = QLabel()
        symbol.setPixmap(QIcon(str(ICONS / icon_name)).pixmap(QSize(ICON_SIZE, ICON_SIZE)))
        symbol.setAlignment(Qt.AlignmentFlag.AlignTop)
        font = radio.font()
        font.setBold(True)
        radio.setFont(font)
        self.body = QVBoxLayout()
        self.body.setSpacing(2)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.addWidget(radio)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)  # kortet är precis så stort som innehållet
        row.setSpacing(10)
        row.addWidget(symbol)
        row.addLayout(self.body, 1)
        radio.toggled.connect(self._mark)

    def _restyle(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    def _mark(self, chosen: bool) -> None:
        self.setProperty("chosen", chosen)
        self._restyle()

    def set_available(self, available: bool) -> None:
        """Ett val som inte går just nu (t.ex. leverans utan inställningar) ritas grått. Själva kortet är inte avstängt: knappen
        till inställningarna och förklaringen ska fungera."""
        self.radio.setEnabled(available)
        self.setProperty("available", available)
        self._restyle()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt
        if self.radio.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.radio.setChecked(True)
        super().mousePressEvent(event)


def _muted(text: str = "") -> QLabel:
    """Förklarande text i dämpad färg."""
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    font = label.font()
    font.setPointSizeF(max(font.pointSizeF() - 1, 7))  # något mindre än rubriken
    label.setFont(font)
    return label


class NgpDialog(QDialog):
    def __init__(self, request: NgpRequest, config_provider: Callable[[], NgpConfig],
                 open_settings: Optional[Callable[[], None]] = None, parent=None,
                 open_validation: Optional[Callable[[], None]] = None, *,
                 controller: Optional[PlanController] = None,
                 request_provider: Optional[Callable[[], NgpRequest]] = None,
                 offer_archive: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Leverans och export")
        self.setWindowIcon(QIcon(str(ICONS / "deliver.svg")))
        self.setMinimumWidth(600)
        self.setStyleSheet(DIALOG_STYLE)
        self.request = request
        self._config_provider = config_provider
        self._open_settings = open_settings
        self._open_validation = open_validation
        self._request_provider = request_provider
        self._offer_archive = offer_archive
        self._switcher = build_plan_switcher(controller, self._switch_plan, self) if controller is not None else None

        self.check_mark = QLabel()  # ✔ ▲ ✘: resultatet av kontrollen med en blick
        self.check_mark.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.check = QLabel()
        self.check.setWordWrap(True)
        self.btn_validate = QPushButton("Kontrollera planen…")
        self.btn_validate.setIcon(QIcon(str(ICONS / "validate.svg")))
        self.btn_validate.setToolTip("Visa avvikelserna mot Lantmäteriets regler och hoppa till dem i kartan.")
        self.btn_validate.clicked.connect(self._validate)
        self.btn_validate.setVisible(open_validation is not None)
        self.archive = QRadioButton("Skapa arkivpaket")
        self.archive_info = _muted("Samlar planen och dess handlingar (plankartan och planbeskrivningen) i ett arkivpaket "
                                   "med bevarandemetadata för långtidsbevarande, enligt Boverkets specifikation. "
                                   "Inget levereras till NGP.")
        self.upload = QRadioButton("Leverera till NGP")
        self.file = QRadioButton("Spara som JSON-fil")
        self.upload_info = QLabel()
        self.upload_info.setWordWrap(True)
        self.upload_info.setTextFormat(Qt.TextFormat.RichText)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet("color: #b3261e;")
        self.btn_settings = QPushButton("Inställningar…")
        self.btn_settings.clicked.connect(self._settings)
        self.understand = QCheckBox("Jag förstår att en godkänd plan publiceras i produktionsmiljön")
        self.file_info = _muted("Skriver leveransen (detaljplan 4.1, application/vnd.lm.detaljplan.v4+json) till en fil. "
                                "Den kan skickas till NGP-supporten för granskning eller laddas upp av en producent.")

        self.group = QButtonGroup(self)  # de tre alternativen ligger i olika kort: koppla ihop dem
        self.group.addButton(self.upload)
        self.group.addButton(self.file)
        self.group.addButton(self.archive)

        self.upload_card = upload_card = ChoiceCard(self.upload, "deliver.svg")
        upload_card.body.addWidget(self.upload_info)
        upload_card.body.addWidget(self.problems)
        settings_row = QHBoxLayout()
        settings_row.addWidget(self.btn_settings)
        settings_row.addStretch(1)
        upload_card.body.addLayout(settings_row)
        upload_card.body.addWidget(self.understand)
        file_card = ChoiceCard(self.file, "file_json.svg")
        file_card.body.addWidget(self.file_info)
        self.archive_box = ChoiceCard(self.archive, "archive.svg")
        self.archive_box.body.addWidget(self.archive_info)
        self.archive_box.setVisible(offer_archive)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        if self._switcher is not None:
            layout.addWidget(self._switcher)
        self.check_box = QGroupBox("Kontroll av planen")
        self.check_box.setObjectName("checkBox")
        check_layout = QVBoxLayout(self.check_box)
        check_row = QHBoxLayout()
        check_row.setSpacing(10)
        check_row.addWidget(self.check_mark)
        check_row.addWidget(self.check, 1)
        check_layout.addLayout(check_row)
        validate_row = QHBoxLayout()
        validate_row.addWidget(self.btn_validate)
        validate_row.addStretch(1)
        check_layout.addLayout(validate_row)
        layout.addWidget(self.check_box)
        layout.addWidget(upload_card)
        layout.addWidget(file_card)
        layout.addWidget(self.archive_box)
        layout.addStretch(1)  # extra höjd ger luft under korten, inte större kort
        layout.addWidget(self.buttons)

        self.upload.toggled.connect(self._update)
        self.file.toggled.connect(self._update)
        self.archive.toggled.connect(self._update)
        self.understand.toggled.connect(self._update)
        self._first = True
        self._forced = False
        self.refresh()
        self.adjustSize()  # så hög som innehållet kräver för dialogens bredd, utan död yta

    # -- innehåll -----------------------------------------------------------------------
    def config(self) -> NgpConfig:
        return self._config_provider()

    def upload_problems(self) -> list[str]:
        """Skäl till att uppladdning inte går: saknad kommun och ofullständiga inställningar."""
        found = []
        if not self.request.kommunkod:
            found.append("Kommunen är inte angiven i planens uppgifter (den avgör vilken producent som levererar).")
        return found + self.config().problems()

    def refresh(self) -> None:
        """Läser om inställningarna (t.ex. efter att inställningarna ändrats) och uppdaterar dialogen."""
        request = self.request
        parts = []
        if request.errors or request.warnings:
            parts.append(f"<b>{request.errors} fel</b> och {request.warnings} varningar. "
                         "Fel stoppar leveransen hos NGP (se Kontrollera planen).")
        else:
            parts.append("inga avvikelser.")
        self.check.setTextFormat(Qt.TextFormat.RichText)
        self.check.setText(f"Planen <b>{esc(request.plan_name or 'utan namn')}</b>: " + " ".join(parts))
        result = ERROR if request.errors else WARNING if request.warnings else GOOD
        mark, colour = MARKS[result]
        self.check_mark.setText(mark)
        self.check_mark.setStyleSheet(f"color: {colour}; font-size: 18px; font-weight: bold; min-width: 20px;")
        self.check_box.setStyleSheet(CHECK_BOX_STYLE % CHECK_COLOURS[result])
        problems = self.upload_problems()
        can_upload = not problems
        self.upload_card.set_available(can_upload)
        self.problems.setText("\n".join(problems))
        self.problems.setVisible(bool(problems))
        self.btn_settings.setVisible(bool(problems) and self._open_settings is not None)
        config = self.config()
        self.upload_info.setText(confirmation_text(config, request.plan_name, request.kommun, request.kommunkod,
                                                   request.errors, request.resuming) if can_upload
                                 else "Leveransen görs via Lantmäteriets Uppdatering-API och kräver producentbehörighet.")
        self.understand.setVisible(config.is_production)
        if not can_upload:
            if not self.archive.isChecked():  # användarens val av arkivpaket ändras inte
                self.file.setChecked(True)
                self._forced = True  # filen valdes av programmet, inte av användaren
        elif self._first or self._forced:
            self.upload.setChecked(True)  # standardval när uppladdning går; användarens eget val ändras inte senare
            self._forced = False
        self._first = False
        self._update()

    def choice(self) -> str:
        if self.archive.isChecked() and self._offer_archive:
            return ARCHIVE
        return UPLOAD if self.upload.isChecked() and self.upload.isEnabled() else FILE

    def _update(self, *_) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self.choice() == UPLOAD:
            ok.setText("Leverera")
            ok.setIcon(QIcon(str(ICONS / "deliver.svg")))
            ok.setEnabled(not self.config().is_production or self.understand.isChecked())
        elif self.choice() == ARCHIVE:
            ok.setText("Skapa arkivpaket…")
            ok.setIcon(QIcon(str(ICONS / "archive.svg")))
            ok.setEnabled(True)
        else:
            ok.setText("Spara fil…")
            ok.setIcon(QIcon(str(ICONS / "file_json.svg")))
            ok.setEnabled(True)
        self.understand.setEnabled(self.choice() == UPLOAD)

    def _validate(self) -> None:
        if self._open_validation is not None:
            self._open_validation()

    def _settings(self) -> None:
        if self._open_settings is not None:
            self._open_settings()
        self.refresh()

    def _switch_plan(self) -> None:
        """Byter till en annan laddad plan (se ``build_plan_switcher``): räknar om ögonblicksbilden (kommun,
        kontrollresultat, om en leverans kan återupptas) för den nya planen i stället för att stänga och öppna
        dialogen igen – till skillnad från t.ex. Planens uppgifter har den inget tillstånd kopplat till en
        specifik plan utöver just ``request``."""
        if self._request_provider is not None:
            self.request = self._request_provider()
        self.refresh()
