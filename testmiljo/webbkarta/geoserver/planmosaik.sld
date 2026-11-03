<?xml version="1.0" encoding="UTF-8"?>
<!-- Samma färger som QGIS-projektet (qgis/skapa_qgis_projekt.py) och Origo-stilen för vektorrutorna. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>planmosaik</Name>
    <UserStyle>
      <Title>Planmosaik</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>Gällande, genomförandetiden pågår</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>visningsstatus</ogc:PropertyName>
            <ogc:Literal>gällande, genomförandetiden pågår</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><CssParameter name="fill">#3b9b6a</CssParameter><CssParameter name="fill-opacity">0.6</CssParameter></Fill>
            <Stroke><CssParameter name="stroke">#3b9b6a</CssParameter><CssParameter name="stroke-width">1.5</CssParameter></Stroke>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>Gällande, genomförandetiden har gått ut</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>visningsstatus</ogc:PropertyName>
            <ogc:Literal>gällande, genomförandetiden har gått ut</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><CssParameter name="fill">#8a94a0</CssParameter><CssParameter name="fill-opacity">0.6</CssParameter></Fill>
            <Stroke><CssParameter name="stroke">#8a94a0</CssParameter><CssParameter name="stroke-width">1.5</CssParameter></Stroke>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>Gällande</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>visningsstatus</ogc:PropertyName>
            <ogc:Literal>gällande</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><CssParameter name="fill">#4a7fc1</CssParameter><CssParameter name="fill-opacity">0.6</CssParameter></Fill>
            <Stroke><CssParameter name="stroke">#4a7fc1</CssParameter><CssParameter name="stroke-width">1.5</CssParameter></Stroke>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>Antagen</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>visningsstatus</ogc:PropertyName>
            <ogc:Literal>antagen</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <PolygonSymbolizer>
            <Fill><CssParameter name="fill">#e0a030</CssParameter><CssParameter name="fill-opacity">0.6</CssParameter></Fill>
            <Stroke><CssParameter name="stroke">#e0a030</CssParameter><CssParameter name="stroke-width">1.5</CssParameter></Stroke>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>Beteckning</Title>
          <TextSymbolizer>
            <Label><ogc:PropertyName>beteckning</ogc:PropertyName></Label>
            <Font><CssParameter name="font-size">11</CssParameter></Font>
            <LabelPlacement><PointPlacement><AnchorPoint>
              <AnchorPointX>0.5</AnchorPointX><AnchorPointY>0.5</AnchorPointY>
            </AnchorPoint></PointPlacement></LabelPlacement>
            <Fill><CssParameter name="fill">#1f2933</CssParameter></Fill>
          </TextSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
