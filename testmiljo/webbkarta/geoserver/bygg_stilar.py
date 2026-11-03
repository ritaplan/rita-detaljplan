"""Skriver GeoServers skalberoende stilar (plan_egenskap.sld och plan_gransar.sld) ur måtten i ../stil.py.

    python geoserver/bygg_stilar.py

plan_anvandning.sld (ytornas färg) beror inte på skalan och är skriven för hand.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import stil  # noqa: E402

HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<!-- {title}. Skriven av bygg_stilar.py ur stil.py: ändra där, inte här. Mått i pixlar, skalade efter kartskalan i band. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>{name}</Name>
    <UserStyle>
      <Title>{title}</Title>
      <FeatureTypeStyle>
"""
TAIL = """      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
"""


def scale_range(lower, upper) -> str:
    text = f"          <MinScaleDenominator>{lower}</MinScaleDenominator>\n" if lower else ""
    if upper:
        text += f"          <MaxScaleDenominator>{upper}</MaxScaleDenominator>\n"
    return text


def equals(field: str, value: str) -> str:
    return (f"          <ogc:Filter><ogc:PropertyIsEqualTo>\n"
            f"            <ogc:PropertyName>{field}</ogc:PropertyName><ogc:Literal>{value}</ogc:Literal>\n"
            f"          </ogc:PropertyIsEqualTo></ogc:Filter>\n")


def line_rules() -> str:
    # Lägst gräns först: GeoServer ritar reglerna i ordning, så den högsta gränsen hamnar överst
    text = ""
    for kind in ("egenskapsgrans", "anvandningsgrans", "planomradesgrans"):
        for lower, upper, scale in stil.bands():
            style = stil.line_style(kind, lower, scale)
            if style is None:
                continue
            dash = (f"              <CssParameter name=\"stroke-dasharray\">"
                    f"{' '.join(str(v) for v in style['dash'])}</CssParameter>\n") if style["dash"] else ""
            text += (f"        <Rule>\n          <Title>{kind} {lower}-{upper or ''}</Title>\n{equals('typ', kind)}"
                     f"{scale_range(lower, upper)}"
                     f"          <LineSymbolizer>\n            <Stroke>\n"
                     f"              <CssParameter name=\"stroke\">#000000</CssParameter>\n"
                     f"              <CssParameter name=\"stroke-width\">{style['width']}</CssParameter>\n{dash}"
                     f"              <CssParameter name=\"stroke-linejoin\">round</CssParameter>\n"
                     f"            </Stroke>\n          </LineSymbolizer>\n        </Rule>\n")
    return text


def pattern_rules() -> str:
    text = ""
    for kind in stil.PATTERNS:
        for lower, upper, scale in stil.bands():
            style = stil.pattern_style(kind, scale)
            if style is None:
                continue
            if style["shape"] == "circle":
                mark = ("<Mark><WellKnownName>circle</WellKnownName>"
                        "<Fill><CssParameter name=\"fill\">#000000</CssParameter></Fill></Mark>")
            else:
                name = "cross" if style["shape"] == "cross" else "circle"
                mark = (f"<Mark><WellKnownName>{name}</WellKnownName><Stroke><CssParameter name=\"stroke\">#000000"
                        f"</CssParameter><CssParameter name=\"stroke-width\">{style['stroke']}</CssParameter>"
                        "</Stroke></Mark>")
            margin = round((style["period"] - style["size"]) / 2, 2)
            text += (f"        <Rule>\n          <Title>{kind} {lower}-{upper or ''}</Title>\n{equals('monster', kind)}"
                     f"{scale_range(lower, upper)}"
                     f"          <PolygonSymbolizer>\n            <Fill><GraphicFill><Graphic>\n              {mark}\n"
                     f"              <Size>{style['size']}</Size>\n            </Graphic></GraphicFill></Fill>\n"
                     f"            <VendorOption name=\"graphic-margin\">{margin}</VendorOption>\n"
                     f"          </PolygonSymbolizer>\n        </Rule>\n")
    return text


for name, title, body in (("plan_gransar", "Gränslinjer", line_rules()),
                          ("plan_egenskap", "Egenskapsytor (mönster)", pattern_rules())):
    (HERE / f"{name}.sld").write_text(HEAD.format(name=name, title=title) + body + TAIL, encoding="utf-8", newline="\n")
    print(f"{name}.sld: {body.count('<Rule>')} regler")
