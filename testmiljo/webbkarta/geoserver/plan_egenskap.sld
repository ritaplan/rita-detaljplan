<?xml version="1.0" encoding="UTF-8"?>
<!-- Egenskapsytor (mönster). Samma utseende som QGIS-projektet (qgis/skapa_qgis_projekt.py) och Origo-stilen för vektorrutorna
     (web/html/planmosaik.js): Boverkets färger, mönster och streckmönster, mått i pixlar. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>plan_egenskap</Name>
    <UserStyle>
      <Title>Egenskapsytor (mönster)</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>Prickmark: marken får inte förses med byggnad</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>prickmark</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>circle</WellKnownName>
                <Fill><CssParameter name="fill">#000000</CssParameter></Fill></Mark>
              <Size>2</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">2.5</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>Korsmark: marken får endast förses med viss typ av byggnadsverk</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>korsmark</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>cross</WellKnownName>
                <Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke></Mark>
              <Size>5</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">4</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>Ringprickad mark: marken får endast förses med byggnadsverk under mark</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>ringprickad</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>circle</WellKnownName>
                <Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">0.8</CssParameter></Stroke></Mark>
              <Size>4</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">4.5</VendorOption>
          </PolygonSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
