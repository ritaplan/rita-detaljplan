# OpenSSF Best Practices-märket

[OpenSSF Best Practices](https://www.bestpractices.dev) är ett märke för öppen källkod. Projektet svarar själv på en
lista med krav (nivån *passing* har ungefär 70 krav) och får ett märke att visa i README. Det är en **självdeklaration**,
ingen granskning av någon utomstående, och det är ingen certifiering. Men det är en känd lista, den är gratis, och den
visar för en kommun att projektet har ordning på rapportering av säkerhetsfel, tester, versionshantering och
kodanalys. Det här dokumentet är underhållarens underlag: vad som redan stämmer, vad som återstår och vad som kan skrivas
i formuläret.

Kraven hämtades 2026-11-03 från [kriterielistan](https://www.bestpractices.dev/en/criteria/0). Kontrollera dem mot
formuläret när du fyller i det; listan kan ha ändrats.

## Gör så här

1. Gå till <https://www.bestpractices.dev> och logga in med GitHub-kontot (det är du som ska logga in; jag kan inte göra det
   åt dig). Välj *Get Your Badge Now* och projektet `ritaplan/rita-detaljplan`.
2. Fyll i formuläret med hjälp av tabellen nedan. Många fält fylls i automatiskt från GitHub.
3. När *passing* är nådd visas märket. Lägg raden som formuläret ger överst i [README.md](../README.md).
4. Förnya svaren när något ändras, till exempel om rapporteringsrutinen ändras.

## Förutsättningar på GitHub (att göra av ägaren)

Dessa inställningar kräver ägarens rättigheter och är ändringar i repots säkerhetsinställningar, så de är inte gjorda:

| Inställning | Var | Varför |
| --- | --- | --- |
| Hemlighetsskanning och push-skydd | *Settings → Advanced Security* (eller *Code security*) | Krav `no_leaked_credentials`; stoppar att nycklar checkas in av misstag. Gratis för publika repon. |
| Dependabot-varningar | samma sida | Meddelar om Actions med kända sårbarheter. |
| Skyddad `main` | *Settings → Rules → Rulesets* eller *Branches* | Kräver att kontrollerna (CodeQL, ruff, bygg) är gröna och stoppar tvångspush. Som enda underhållare kan du låta ägaren kringgå regeln. Ger poäng i Scorecard. |
| Tvåfaktorsinloggning | GitHub-kontot | Skyddar pluginkällan som läses direkt från `main` (se [Leveranskedja](sakerhet.md#leveranskedja-och-distribution)). |
| Privat sårbarhetsrapportering | *Settings → Advanced Security* | Är redan påslagen (kontrollerad 2026-11-03). |

## Kraven på nivån *passing* och läget för projektet

**Ja** = uppfyllt idag. **Efter push** = uppfylls när ändringarna i den här omgången är pushade och körs på GitHub.
**Underhållaren** = svaret är en bedömning som bara du kan ge.

### Grunder

| Krav | Läge | Underlag |
| --- | --- | --- |
| `homepage_url`, `description_good`, `interact`, `contribution` | Ja | <https://ritaplan.xyz>, [README](../README.md), [CONTRIBUTING](../CONTRIBUTING.md) |
| `contribution_requirements` | Ja | CONTRIBUTING (kodstil, test, ändringslogg) |
| `floss_license`, `floss_license_osi`, `license_location` | Ja | GPL-2.0-or-later, [LICENSE](../LICENSE) i rotkatalogen |
| `documentation_basics`, `documentation_interface` | Ja | [Användarhandbok](anvandning.md), [handbok](handbok/), [säkerhet](sakerhet.md) |
| `sites_https` | Ja | GitHub och ritaplan.xyz använder https |
| `discussion` | Ja | GitHub Issues (sökbara, med adress) |
| `english` | Delvis (SHOULD) | Dokumentationen och gränssnittet är på svenska. Skriv i formuläret att felrapporter och kommentarer tas emot på engelska om du står för det, och att dokumentationen är på svenska av målgruppsskäl (svenska kommuner, svenska regelverk). |
| `maintained` | Underhållaren | Projektet har aktiv utveckling (kolla senaste commit). |

### Ändringskontroll

| Krav | Läge | Underlag |
| --- | --- | --- |
| `repo_public`, `repo_track`, `repo_interim`, `repo_distributed` | Ja | Publikt git-repo på GitHub med hela historiken |
| `version_unique`, `version_semver`, `version_tags` | Ja | Versionsnummer `0.1.x` i `metadata.txt`, taggar `v0.1.x` |
| `release_notes` | Ja | [CHANGELOG.md](../CHANGELOG.md) och texten på varje release |
| `release_notes_vulns` | Ja | Rättade säkerhetsfel anges under rubriken *Säkerhet* i ändringsloggen (så gjordes i 0.1.75). Inga kända fel med CVE-nummer finns, svara *N/A* eller *Met* enligt formulärets text. |

### Rapportering

| Krav | Läge | Underlag |
| --- | --- | --- |
| `report_process`, `report_tracker`, `report_archive` | Ja | GitHub Issues med mallar i `.github/ISSUE_TEMPLATE/` |
| `report_responses`, `enhancement_responses` | Underhållaren | Svara på ärenden inom rimlig tid. Finns inga ärenden alls, läs formulärets förklaring av hur kravet ska besvaras. |
| `vulnerability_report_process`, `vulnerability_report_private` | Ja | [SECURITY.md](../SECURITY.md) med privat rapportering via GitHub |
| `vulnerability_report_response` | Underhållaren | Löftet i SECURITY.md är första svar inom 14 dagar. Ändra texten om du inte vill lova det. |

### Kvalitet

| Krav | Läge | Underlag |
| --- | --- | --- |
| `build`, `build_common_tools`, `build_floss_tools` | Ja | `python tools/build_zip.py` (bara Python). Reproducerbart. |
| `test`, `test_invocation` | Ja | `tests\run_tests.bat` (Pythons `unittest` i QGIS Python), beskrivet i CONTRIBUTING |
| `test_most`, `test_continuous_integration` | Delvis (SUGGESTED) | Testsviten är stor men kräver QGIS 4 och körs lokalt, inte på GitHub. Skriv det. |
| `test_policy`, `tests_are_added`, `tests_documented_added` | Ja | CONTRIBUTING: *Ny funktion eller rättning ska ha ett test*. Exempel: fynd 6 i 0.1.75 har ett test. |
| `warnings`, `warnings_fixed` | Efter push | ruff-kontrollen (`ruff.toml`, regler E9 och F utom oanvända importer och variabler) körs i `build-check.yml`. Första körningen 2026-11-03 gav bara fynd om oanvända importer och variabler; de ignoreras medvetet. |
| `warnings_strict` | Delvis (SUGGESTED) | Reglerna är avsiktligt snäva (riktiga fel, inte stil). |

### Säkerhet

| Krav | Läge | Underlag |
| --- | --- | --- |
| `know_secure_design`, `know_common_errors` | Underhållaren | Du intygar att minst en utvecklare känner till säker design och vanliga fel (injektion, otillförlitlig indata, hemligheter). [Säkerhetsbeskrivningen](sakerhet.md) visar hur de har tillämpats (identifierare och literaler i SQL, https-krav, ingen dynamisk kodkörning). Bedöm själv om du kan intyga det. |
| `crypto_*` (published, call, floss, keylength, working, weaknesses, pfs, password_storage, random) | N/A | Pluginet har ingen egen kryptografi: all kryptering (https, databasanslutning) sköts av QGIS/Qt, och lösenord lagras av QGIS autentiseringsdatabas. |
| `delivery_mitm`, `delivery_unsigned` | Ja | Allt hämtas över https från GitHub. Ingen kontrollsumma hämtas över http. |
| `vulnerabilities_fixed_60_days`, `vulnerabilities_critical_fixed` | Ja | Inga kända öppna sårbarheter över 60 dagar (fynd i [sakerhet.md](sakerhet.md): bara informativa kvar). |
| `no_leaked_credentials` | Efter push | Slå på hemlighetsskanning (se ovan). Repot har inte sökts igenom med verktyg; gör det innan du svarar. |

### Analys

| Krav | Läge | Underlag |
| --- | --- | --- |
| `static_analysis`, `static_analysis_common_vulnerabilities`, `static_analysis_often` | Efter push | CodeQL (`security-extended`) i `.github/workflows/codeql.yml`, vid varje ändring i `main` och varje vecka |
| `static_analysis_fixed` | Efter push | Rätta fynd från CodeQL som är medel eller högre. Första körningen visar vad som finns. |
| `dynamic_analysis` och de som hör till (SUGGESTED, utom `dynamic_analysis_fixed`) | Nej | Ingen fuzzning eller dynamisk analys finns. `dynamic_analysis_fixed` är *N/A* om ingen sådan analys körs. Att fuzza filläsarna (`geometri.py`, `planbeskrivning_docx.py`) vore ett bra nästa steg. |

## Efter passing: nästa nivåer

Märket har också nivåerna *silver* och *gold*. De kräver bland annat signerade releaser, en andra underhållare, en
dokumenterad säkerhetsgranskning av en utomstående och mer. Det är rimligt att vänta med dem tills projektet har fler
medverkande.
