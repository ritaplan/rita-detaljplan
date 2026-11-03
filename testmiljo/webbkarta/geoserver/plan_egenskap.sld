<?xml version="1.0" encoding="UTF-8"?>
<!-- Egenskapsytor (mönster). Skriven av bygg_stilar.py ur stil.py: ändra där, inte här. Mått i pixlar, skalade efter kartskalan i band. -->
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
          <Title>prickmark 0-1500</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>prickmark</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>1500</MaxScaleDenominator>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#000000</CssParameter></Fill></Mark>
              <Size>1.6</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">2.75</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>prickmark 1500-3000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>prickmark</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>1500</MinScaleDenominator>
          <MaxScaleDenominator>3000</MaxScaleDenominator>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#000000</CssParameter></Fill></Mark>
              <Size>1.2</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">2.25</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>korsmark 0-1500</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>korsmark</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>1500</MaxScaleDenominator>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>cross</WellKnownName><Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke></Mark>
              <Size>4.5</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">4.0</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>korsmark 1500-3000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>korsmark</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>1500</MinScaleDenominator>
          <MaxScaleDenominator>3000</MaxScaleDenominator>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>cross</WellKnownName><Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke></Mark>
              <Size>2.12</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">2.25</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>ringprickad 0-1500</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>ringprickad</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>1500</MaxScaleDenominator>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>circle</WellKnownName><Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">0.6</CssParameter></Stroke></Mark>
              <Size>4.0</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">4.0</VendorOption>
          </PolygonSymbolizer>
        </Rule>
        <Rule>
          <Title>ringprickad 1500-3000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>monster</ogc:PropertyName><ogc:Literal>ringprickad</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>1500</MinScaleDenominator>
          <MaxScaleDenominator>3000</MaxScaleDenominator>
          <PolygonSymbolizer>
            <Fill><GraphicFill><Graphic>
              <Mark><WellKnownName>circle</WellKnownName><Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke></Mark>
              <Size>1.89</Size>
            </Graphic></GraphicFill></Fill>
            <VendorOption name="graphic-margin">2.25</VendorOption>
          </PolygonSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
