# froide-mcp — mitä tapahtui ja mitä tehdään seuraavaksi

## Missä mennaan nyt

Release `v1.0.0` on julkaistu 2026-06-30. Muutama asia on jäänyt puoliksi tai
vaatii välittömän korjauksen ennen kuin release on oikeasti "valmis".

---

## 🔴 Välittömät korjaukset (ennen kuin jatketaan)

### 1. Release on merkitty pre-releaseksi — korjaa

GitHub-releasessa `v1.0.0` on lippu `prerelease: true`. Se tarkoittaa, että
GitHub ei esitä tätä repon "latest release" -versioksi ja käyttäjät näkevät
varoituslipun. Jos tämä on tarkoitettu ensimmäiseksi vakaaksi versioksi,
lippu pitää poistaa.

```bash
gh release edit v1.0.0 --prerelease=false --repo jaakkokorhonen/froide-mcp
```

### 2. CHANGELOG.md on vanhentunut — päivitä

`CHANGELOG.md` on edelleen `[Unreleased] — v0.1.0`. Se ei vastaa tagia
`v1.0.0`. Korjaus:

```diff
-## [Unreleased] — v0.1.0
+## [v1.0.0] — 2026-06-30
```

Ja viimeiset rivit:

```diff
-[Unreleased]: https://github.com/jaakkokorhonen/froide-mcp/compare/HEAD...HEAD
+[v1.0.0]: https://github.com/jaakkokorhonen/froide-mcp/releases/tag/v1.0.0
```

### 3. `__init__.py`:n versio ei vastaa `pyproject.toml`:ia — yhtänlaistä

`pyproject.toml` sanoo `version = "1.0.0"`, mutta
`froide_mcp/__init__.py` sanoo `__version__ = "0.1.0"`. Molemmat pitää
osoittaa samaan paikkaan. Yksinkertaisin ratkaisu on lukea versio
`pyproject.toml`:sta:

```python
# froide_mcp/__init__.py
"""Froide MCP server."""
try:
    from importlib.metadata import version
    __version__ = version("froide-mcp")
except Exception:
    __version__ = "unknown"
```

### 4. Issue #12 on auki — sulje

Issue #12 "Release v1.0.0" on edelleen auki vaikka release on tehty.
Sulje se viittaamalla tagiin:

```bash
gh issue close 12 \
  --comment "Release v1.0.0 julkaistu: https://github.com/jaakkokorhonen/froide-mcp/releases/tag/v1.0.0" \
  --repo jaakkokorhonen/froide-mcp
```

---

## 🟡 Tärkeää ennen ensimmäistä yötä

### 5. `SMOKE_SESSION_TOKEN` — varmista rotaatio

Token vanhenee 8 tunnin kuluttua kirjautumisesta. Nightly monitoring ajaa
kello 04:00 UTC (07:00 EEST). Jos token on asetettu aamuisin, se on
vanhennut ennen ensimmäistä ajoa.

```bash
# Hae tuore token
open https://<MCP_SERVICE_URL>/auth/login
# Kirjaudu → kopioi {"session_token": "eyJ..."}

gh secret set SMOKE_SESSION_TOKEN --repo jaakkokorhonen/froide-mcp
```

Token pitää uusia ennen jokaista nightly-ajoa, tai ottaa käyttöön
pitkaikestoisempi autentikaatiomekanismi (ks. alla: v1.1.0 ehdotukset).

### 6. Varmista, että `cd.yml`-pipeline ajoi onnistuneesti tagin jälkeen

Tagi `v1.0.0` triggeröi `cd.yml`:n. Tarkista:

**GitHub → Actions → Deploy** — etsi ajot joissa ref on `refs/tags/v1.0.0`.
Kaikkien neljän vaiheen (Build → Push → Deploy → Smoke) täytyy olla vihreinä.

Jos smoke-testit skippasivat (`SKIPPED`) eikä yhtaan testiä ajanut, syynä on
lähes varmasti puuttuva `SMOKE_SESSION_TOKEN`.

---

## 🔵 v1.1.0 — ehdotetut seuraavat askeleet

Nämä eivät ole kiireellisiä, mutta tekevät releasesta kestävämmän.

### Smoke-tokenin rotaation automatisointi

Manuaalinen 8 h rotaatio ei skaalaudu. Vaihtoehdot:

| Vaihtoehto | Kuvaus | Työmäärä |
|---|---|---|
| Service account -token | Froide OAuth2 `client_credentials` grant suoraan `nightly.yml`:ssä | Pieni — 1–2 h |
| Token refresh endpoint | `/auth/refresh` joka ottaa vanhan tokenin ja palauttaa uuden | Keskisuuri |
| Lyhytkestoisempi smoke | Testaa vain `/healthz` ilman sessiota | Triviaali, mutta heikentää testitasoa |

Suositus: **service account -token** `nightly.yml`:ssä — hae token
`client_credentials`-grantilla Froide OAuth2:sta, ei tarvita interaktiivista
kirjautumista.

### JWT JWKS-verifikaatio

`auth.py` dekoodaa Google ID tokenin ilman allekirjoituksen verifikaatiota
(dokumentoitu `docs/deployment.md`:ssä). Ennen laajempaa käyttöä tämä
kannattaa korjata:

```python
# Lisää riippuvuus: google-auth>=2.0
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

id_info = id_token.verify_oauth2_token(
    token, google_requests.Request(), GOOGLE_CLIENT_ID
)
```

### `docs/orchestration.md` — viisi puuttuvaa työkalua

Dokumentissa on vielä "Planned tools" -osio vaikka kaikki kahdeksan on jo
toteutettu. Lisää parametritaulukot viidelle puuttuvalle:
`draft_followup_for_request`, `preflight_request_submission`,
`get_request_analytics`, `draft_request`, `followup_after_deadline`.

---

## Yhteenveto — nopeat korjaukset järjestyksessä

| # | Toimenpide | Komento / sijainti |
|---|---|---|
| 1 | Poista pre-release -lippu | `gh release edit v1.0.0 --prerelease=false` |
| 2 | Päivitä `CHANGELOG.md` | `[Unreleased]` → `[v1.0.0]` + päivämäärä |
| 3 | Yhtänlaistä `__init__.py` versio | Lue `importlib.metadata` |
| 4 | Sulje issue #12 | `gh issue close 12` |
| 5 | Rotoi `SMOKE_SESSION_TOKEN` | `/auth/login` → uusi secret |
| 6 | Tarkista `cd.yml`-ajon tulos tagille | Actions → Deploy → `refs/tags/v1.0.0` |
