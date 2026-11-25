"""Inställning anslutning NGP: en flik för Produktion, en för Verifiering och en för Sökning, var och en med egen adress,
egen nyckel och en kontroll som visar om anslutningen är aktiv. (Referensskalan ställs in i Planens uppgifter,
teckenförklaringen i layoutläget.)"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                                 QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ..core import ngp_client as ngp
from ..core import settings
from .richtext import esc

GREEN, RED, GREY = "#1b7f3b", "#b3261e", "#7a7a7a"
ORDER = ("prod", "ver")  # flikarna för leverans, i den ordning de visas
NOT_CHECKED = "Inte kontrollerad."


def _dot(colour: str) -> QIcon:
    """En liten färgad prick: hälsan på en flik, så att man ser alla tre i en blick."""
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pixmap)


def _key_combo(first_label: str, current: str) -> QComboBox:
    """Listan över QGIS autentiseringskonfigurationer. En sparad konfiguration som tagits bort visas ändå."""
    combo = QComboBox()
    combo.addItem(first_label, "")
    for cid, name in settings.auth_configs():
        combo.addItem(f"{name} ({cid})", cid)
    if current and combo.findData(current) < 0:
        combo.addItem(current, current)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    return combo


class _Tab(QWidget):
    """Det som alla flikar har gemensamt: en nyckel, en kontrollknapp och en rad som visar hur anslutningen mår."""

    def __init__(self):
        super().__init__()
        self.form = QFormLayout()
        self.check = QPushButton("Kontrollera anslutningen")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setEnabled(False)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addLayout(self.form)
        row = QHBoxLayout()
        row.addWidget(self.check)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.health: Optional[ngp.Health] = None
        self.show_health(None)

    def show_health(self, health: Optional["ngp.Health"]) -> None:
        self.health = health
        if health is None:
            self.status.setText(f"<span style='color:{GREY}'>● {NOT_CHECKED}</span>")
        else:
            colour = GREEN if health.ok else RED
            self.status.setText(f"<span style='color:{colour}'>● {esc(health.text)}</span>")


class _DeliveryTab(_Tab):
    """Leverans till en miljö: adress till API:et, adress till tokentjänsten och nyckeln (autentiseringskonfigurationen)."""

    def __init__(self, config: "ngp.NgpConfig"):
        super().__init__()
        self.environment = config.environment
        self.base = QLineEdit(config.base_url)
        self.token = QLineEdit(config.token_url)
        self.token.setPlaceholderText("tomt = ingen inloggning")
        self.auth = _key_combo("(ingen vald)", config.authcfg)
        self.reset = QPushButton("Standardadresser")
        self.reset.setToolTip("Sätter tillbaka adresserna Lantmäteriet anger för miljön.")
        self.form.addRow("Adress till API:et", self.base)
        self.form.addRow("Adress till tokentjänsten", self.token)
        self.form.addRow("Nyckel", self.auth)
        self.form.addRow("", self.reset)
        self.note.setText("Leverans kräver en nyckel med producentbehörighet. Nyckel och hemlighet från Lantmäteriets "
                          "API-portal lagras i QGIS autentiseringsdatabas: lägg till en konfiguration av typen "
                          "<i>Grundläggande autentisering</i> under Inställningar → Alternativ → Autentisering (nyckeln "
                          "som användarnamn, hemligheten som lösenord) och välj den här. Leverans till NGP är inte "
                          "verifierad mot Lantmäteriets miljö.")
        self.reset.clicked.connect(self.use_standard_addresses)

    def use_standard_addresses(self) -> None:
        env = ngp.ENVIRONMENTS.get(self.environment)
        if env is not None:
            self.base.setText(env.base_url)
            self.token.setText(env.token_url)

    def config(self) -> "ngp.NgpConfig":
        return ngp.NgpConfig(environment=self.environment, base_url=self.base.text().strip(),
                             token_url=self.token.text().strip(), authcfg=self.auth.currentData() or "")


class _SearchTab(_Tab):
    """Sökning: frågar Sök-API:et om en plan finns i NGP. Det räcker med en konsumentnyckel för datamängden Detaljplan."""

    def __init__(self, config: "ngp.NgpConfig"):
        super().__init__()
        self.env = QComboBox()
        for key in ORDER:
            self.env.addItem(ngp.ENVIRONMENTS[key].title, key)
        self.env.setCurrentIndex(max(0, self.env.findData(config.environment)))
        self.auth = _key_combo("(samma nyckel som leveransen i den miljön)", config.search_authcfg)
        self.address = QLineEdit()
        self.address.setReadOnly(True)
        self.form.addRow("Fråga i miljön", self.env)
        self.form.addRow("Nyckel (konsument)", self.auth)
        self.form.addRow("Adress till sökningen", self.address)
        self.note.setText("Databashanteraren frågar Lantmäteriets Sök-API om en plan finns i NGP. Det räcker med en "
                          "konsumentnyckel för datamängden Detaljplan: en kommun som är producent har oftast både "
                          "konsument- och producentnyckel. Adressen och tokentjänsten hämtas från fliken för miljön.")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inställning anslutning NGP")
        self.setMinimumWidth(600)
        active = settings.active_ngp_environment()
        configs = {key: settings.ngp_environment_config(key) for key in ORDER}
        if active == "egen":  # en tidigare egen adress flyttas till Verifiering (som den var tänkt för)
            configs["ver"] = replace(settings.ngp_environment_config("egen"), environment="ver")
            active = "ver"
        search = settings.ngp_search_config()
        if search.environment == "egen":
            search = replace(search, environment="ver")
        self.delivery = {key: _DeliveryTab(configs[key]) for key in ORDER}
        self.search = _SearchTab(search)
        self.ngp_env = QComboBox()  # miljön leveransen går till
        for key in ORDER:
            self.ngp_env.addItem(ngp.ENVIRONMENTS[key].title, key)
        self.ngp_env.setCurrentIndex(max(0, self.ngp_env.findData(active)))
        self.tabs = QTabWidget()
        for key in ORDER:
            self.tabs.addTab(self.delivery[key], ngp.ENVIRONMENTS[key].title)
        self.tabs.addTab(self.search, "Sökning")
        self.check_all_button = QPushButton("Kontrollera alla")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Spara")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        head = QHBoxLayout()
        head.addWidget(QLabel("Leverans går till"))
        head.addWidget(self.ngp_env)
        head.addStretch(1)
        foot = QHBoxLayout()
        foot.addWidget(self.check_all_button)
        foot.addStretch(1)
        foot.addWidget(self.buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(head)
        layout.addWidget(self.tabs)
        layout.addLayout(foot)

        for key in ORDER:
            self.delivery[key].check.clicked.connect(lambda _=False, k=key: self.check_delivery(k))
        self.search.check.clicked.connect(self.check_search)
        self.check_all_button.clicked.connect(self.check_all)
        self.search.env.currentIndexChanged.connect(self._show_search_address)
        for key in ORDER:
            self.delivery[key].base.textChanged.connect(self._show_search_address)
        self._show_search_address()
        for index in range(self.tabs.count()):
            self.tabs.setTabIcon(index, _dot(GREY))

    # -- vad som är valt -------------------------------------------------------------------------
    def delivery_config(self, environment: str) -> "ngp.NgpConfig":
        return self.delivery[environment].config()

    def ngp_config(self) -> "ngp.NgpConfig":
        """Inställningarna för den miljö leveransen går till."""
        return self.delivery_config(self.ngp_env.currentData())

    def search_config(self) -> "ngp.NgpConfig":
        """Inställningarna för sökningen: miljöns adresser, med sökningens egen nyckel om en är vald."""
        return replace(self.delivery_config(self.search.env.currentData()),
                       search_authcfg=self.search.auth.currentData() or "")

    def _show_search_address(self, *_) -> None:
        self.search.address.setText(self.search_config().search_url)

    # -- kontroll av anslutningarna ------------------------------------------------------------------
    def _checked(self, tab: _Tab, index: int, health: "ngp.Health") -> "ngp.Health":
        tab.show_health(health)
        self.tabs.setTabIcon(index, _dot(GREEN if health.ok else RED))
        return health

    def check_delivery(self, environment: str) -> "ngp.Health":
        """Kontrollerar leveransen till en miljö: loggar in och ber tjänsten om hälsan. Blockerar kort medan anropen görs."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            health = self._client(self.delivery_config(environment)).check()
        finally:
            QApplication.restoreOverrideCursor()
        return self._checked(self.delivery[environment], ORDER.index(environment), health)

    def check_search(self) -> "ngp.Health":
        """Kontrollerar sökningen: loggar in och läser vilka kommuner nyckeln ser."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            health = self._search_client(self.search_config()).check()
        finally:
            QApplication.restoreOverrideCursor()
        return self._checked(self.search, len(ORDER), health)

    def check_all(self) -> None:
        """Kontrollerar de anslutningar som har en nyckel vald (de andra är inte i bruk)."""
        for key in ORDER:
            if self.delivery[key].auth.currentData():
                self.check_delivery(key)
        if self.search.auth.currentData() or self.delivery[self.search.env.currentData()].auth.currentData():
            self.check_search()

    def _client(self, config: "ngp.NgpConfig") -> "ngp.NgpClient":  # särskilt för att kunna bytas ut i tester
        return ngp.NgpClient(config)

    def _search_client(self, config: "ngp.NgpConfig") -> "ngp.NgpSearchClient":  # likaså
        return ngp.NgpSearchClient(config)

    def accept(self):
        for key in ORDER:
            settings.set_ngp_config(self.delivery_config(key))
        settings.set_ngp_active(self.ngp_env.currentData())
        settings.set_ngp_search(self.search.env.currentData(), self.search.auth.currentData() or "")
        super().accept()
