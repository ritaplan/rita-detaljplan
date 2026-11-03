<?xml version="1.0" encoding="UTF-8"?>
<!-- Gränslinjer. Samma utseende som QGIS-projektet (qgis/skapa_qgis_projekt.py) och Origo-stilen för vektorrutorna
     (web/html/planmosaik.js): Boverkets färger, mönster och streckmönster, mått i pixlar. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>plan_gransar</Name>
    <UserStyle>
      <Title>Gränslinjer</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>Egenskapsgräns</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>egenskapsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1</CssParameter>
              <CssParameter name="stroke-dasharray">10 4 2 4 2 4</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>Användningsgräns</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>anvandningsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">2</CssParameter>
              <CssParameter name="stroke-dasharray">10 2 1 2</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>Planområdesgräns</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">3</CssParameter>
              <CssParameter name="stroke-dasharray">16 4 4 4 16 4</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
