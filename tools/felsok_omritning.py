"""Felsökning: räknar vad som begär omritning av kartan i QGIS och vad som ändrar kartans utsnitt. Körs i QGIS
Python-konsol (inte som plugin). Starta om QGIS först om du har provat en tidigare version av skriptet.

    exec(open(r"C:\\dev\\detaljplan-qgis-temp\\tools\\felsok_omritning.py", encoding="utf-8").read())

Öppna sedan planen, vänta en halv minut utan att röra kartan och skriv  rapport()  i konsolen. Skriptet ändrar
ingenting i QGIS eller planen, det lyssnar bara på signaler.
"""
import time
from collections import Counter

from qgis.core import QgsProject
from qgis.utils import iface

_raknare = Counter()
_logg = []
_start = time.time()
_bevakade = set()
_karta = iface.mapCanvas()


def _tid():
    return round(time.time() - _start, 1)


def _notera(namn):
    def anrop(*_):
        _raknare[namn] += 1
        _logg.append((_tid(), namn))
    return anrop


def _statusradens_hojd():
    try:
        return iface.mainWindow().statusBar().height()
    except Exception:  # noqa: BLE001 - bara för felsökning
        return None


def _utsnitt_andrat(*_):
    """Skriver ner kartfönstrets storlek, skalan och mittpunkten: skiljer en storleksändring från en zoomning."""
    ruta = _karta.extent()
    _raknare["utsnitt ändrat"] += 1
    _logg.append((_tid(), "utsnitt", f"fönster {_karta.width()}x{_karta.height()}", f"skala {_karta.scale():.2f}",
                  f"mitt {ruta.center().x():.2f}, {ruta.center().y():.2f}", f"statusrad {_statusradens_hojd()}"))


def _bevaka(lager):
    if lager.id() in _bevakade:
        return
    _bevakade.add(lager.id())
    lager.repaintRequested.connect(_notera("repaint: " + lager.name()))
    lager.dataChanged.connect(_notera("dataChanged: " + lager.name()))


def _lager_tillagda(lista):
    _raknare["lager tillagda"] += len(lista)
    _logg.append((_tid(), "lager tillagda", [x.name() for x in lista]))
    for x in lista:
        _bevaka(x)


_karta.renderStarting.connect(_notera("ritning startar"))
_karta.extentsChanged.connect(_utsnitt_andrat)
_karta.scaleChanged.connect(_notera("skala ändrad"))
_karta.destinationCrsChanged.connect(_notera("kartans koordinatsystem ändrat"))
for _lager in QgsProject.instance().mapLayers().values():
    _bevaka(_lager)
QgsProject.instance().layersAdded.connect(_lager_tillagda)
QgsProject.instance().layersRemoved.connect(_notera("lager borttagna"))
QgsProject.instance().crsChanged.connect(_notera("projektets koordinatsystem ändrat"))


def rapport():
    print("Antal:", dict(_raknare))
    print("De sista händelserna (sekunder sedan start, vad):")
    for rad in _logg[-30:]:
        print("  ", rad)


print("Lyssnar. Öppna planen, vänta en halv minut utan att röra kartan och skriv  rapport()")
