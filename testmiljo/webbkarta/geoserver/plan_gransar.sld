<?xml version="1.0" encoding="UTF-8"?>
<!-- Gränslinjer. Skriven av bygg_stilar.py ur stil.py: ändra där, inte här. Mått i pixlar, skalade efter kartskalan i band. -->
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
          <Title>egenskapsgrans 0-1500</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>egenskapsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>1500</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.0</CssParameter>
              <CssParameter name="stroke-dasharray">10.0 4.0 2.0 4.0 2.0 4.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>egenskapsgrans 1500-3000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>egenskapsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>1500</MinScaleDenominator>
          <MaxScaleDenominator>3000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">0.5</CssParameter>
              <CssParameter name="stroke-dasharray">4.71 1.89 0.94 1.89 0.94 1.89</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>egenskapsgrans 3000-6000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>egenskapsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>3000</MinScaleDenominator>
          <MaxScaleDenominator>6000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">0.5</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>anvandningsgrans 0-1500</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>anvandningsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>1500</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">2.0</CssParameter>
              <CssParameter name="stroke-dasharray">10.0 2.0 1.0 2.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>anvandningsgrans 1500-3000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>anvandningsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>1500</MinScaleDenominator>
          <MaxScaleDenominator>3000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">0.94</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>anvandningsgrans 3000-6000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>anvandningsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>3000</MinScaleDenominator>
          <MaxScaleDenominator>6000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">0.6</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>anvandningsgrans 6000-12000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>anvandningsgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>6000</MinScaleDenominator>
          <MaxScaleDenominator>12000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">0.6</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 0-1500</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>1500</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">3.0</CssParameter>
              <CssParameter name="stroke-dasharray">16.0 4.0 4.0 4.0 16.0 4.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 1500-3000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>1500</MinScaleDenominator>
          <MaxScaleDenominator>3000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.41</CssParameter>
              <CssParameter name="stroke-dasharray">7.54 1.89 1.89 1.89 7.54 1.89</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 3000-6000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>3000</MinScaleDenominator>
          <MaxScaleDenominator>6000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 6000-12000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>6000</MinScaleDenominator>
          <MaxScaleDenominator>12000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 12000-24000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>12000</MinScaleDenominator>
          <MaxScaleDenominator>24000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 24000-48000</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>24000</MinScaleDenominator>
          <MaxScaleDenominator>48000</MaxScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
        <Rule>
          <Title>planomradesgrans 48000-</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo>
            <ogc:PropertyName>typ</ogc:PropertyName><ogc:Literal>planomradesgrans</ogc:Literal>
          </ogc:PropertyIsEqualTo></ogc:Filter>
          <MinScaleDenominator>48000</MinScaleDenominator>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#000000</CssParameter>
              <CssParameter name="stroke-width">1.0</CssParameter>
              <CssParameter name="stroke-linejoin">round</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
