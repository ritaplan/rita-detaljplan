<?xml version="1.0" encoding="UTF-8"?>
<!-- Användningsytor. Samma utseende som QGIS-projektet (qgis/skapa_qgis_projekt.py) och Origo-stilen för vektorrutorna
     (web/html/planmosaik.js): Boverkets färger, mönster och streckmönster, mått i pixlar. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>plan_anvandning</Name>
    <UserStyle>
      <Title>Användningsytor</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>Användning (Boverkets färg)</Title>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill"><ogc:PropertyName>fyllfarg</ogc:PropertyName></CssParameter>
              <CssParameter name="fill-opacity">0.75</CssParameter>
            </Fill>
          </PolygonSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
