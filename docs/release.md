# froide-mcp v0.1.0 — release-ohje

Tämä dokumentti kuvaa kaikki vaiheet ensimmäisen tuotantoreleasen tekemiseksi.
Vaiheet ovat järjestyksessä: jokainen askel on edellisen edellytys.

---

## Esivalmistelut

Ennen tagia varmistetaan, että infrastruktuuri, secretit ja manuaalinen
deploy-testi ovat kunnossa. Tagi triggeröi `cd.yml`:n automaattisesti — jos
ympäristö ei ole valmis, deploy epäonnistuu.

---

## Vaihe 1 — Workload Identity Federation

> Jos `froide-infra`-projektin WIF-pool on jo olemassa, siirry suoraan
> kohtaan *Reuse existing pool* dokumentissa `docs/workload_identity.md`.

Luo WIF-pool, OIDC-provider ja deploy-palvelutili joko Terraformilla tai
`gcloud`-komennoilla. Täydet ohjeet: **`docs/workload_identity.md`**.

Tallenna kaksi tulosta myöhempää vaihetta varten:

```bash
terraform output wif_provider    # → GCP_WORKLOAD_IDENTITY_PROVIDER
terraform output deploy_sa_email # → GCP_SERVICE_ACCOUNT
```

---

## Vaihe 2 — Terraform (infra)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Täytä muuttujat:
#   project_id         = "your-gcp-project-id"
#   region             = "europe-north1"
#   froide_service_url = "https://froide-xxxx.run.app"
#   allowed_hd         = ""          # tyhjä = mikä tahansa Google-tili
#   mcp_base_url       = ""          # jätetään tyhjäksi ensimmäisellä ajolla

terraform init
terraform plan
terraform apply
```

Ensimmäinen apply luo Cloud Run -palvelun ja tulostaa sen URL:n:

```bash
terraform output mcp_service_url
# esim. https://froide-mcp-abcd1234-lm.a.run.app
```

**Kopioi URL ja aja Terraform uudelleen** niin että `MCP_BASE_URL`-ympäristömuuttuja
kirjautuu Cloud Runiin oikein (tarvitaan Google OAuth `redirect_uri`:ta varten):

```bash
# terraform.tfvars — päivitä mcp_base_url
mcp_base_url = "https://froide-mcp-abcd1234-lm.a.run.app"

terraform apply   # toinen ajo — pelkkä MCP_BASE_URL päivittyy
```

---

## Vaihe 3 — Google OAuth2 Client

1. **Google Cloud Console → APIs & Services → Credentials → Create Credentials
   → OAuth 2.0 Client ID → Web application**
2. Authorized redirect URIs:
   ```
   https://froide-mcp-abcd1234-lm.a.run.app/auth/callback
   ```
3. Tallenna **Client ID** ja **Client Secret**.

---

## Vaihe 4 — Froide OAuth2 Application

Froide Django Admin (`/admin/account/application/add/`):

| Kenttä | Arvo |
|---|---|
| Client type | Confidential |
| Authorization grant type | Client credentials |
| Name | froide-mcp |
| Scopes | `read:request read:profile make:request` |

Tallenna **Client ID** ja **Client Secret**.

---

## Vaihe 5 — Secret Manager -arvot

```bash
export PROJECT=your-gcp-project-id

echo -n "<google-client-id>"     | gcloud secrets versions add froide-mcp-google-client-id     --data-file=- --project=$PROJECT
echo -n "<google-client-secret>" | gcloud secrets versions add froide-mcp-google-client-secret --data-file=- --project=$PROJECT
echo -n "<froide-client-id>"     | gcloud secrets versions add froide-mcp-froide-client-id     --data-file=- --project=$PROJECT
echo -n "<froide-client-secret>" | gcloud secrets versions add froide-mcp-froide-client-secret --data-file=- --project=$PROJECT
openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add froide-mcp-session-secret --data-file=- --project=$PROJECT
```

Secret Manager -resurssit luo Terraform (vaihe 2). Arvot täytetään vasta tässä.

---

## Vaihe 6 — GitHub Actions -secretit ja -variablet

Täydet ohjeet: **`docs/github_actions_secrets.md`**.

```bash
# Secretit
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo jaakkokorhonen/froide-mcp
gh secret set GCP_SERVICE_ACCOUNT            --repo jaakkokorhonen/froide-mcp
# SMOKE_SESSION_TOKEN asetetaan vaiheessa 8

# Variablet
gh variable set GCP_REGION      --body "europe-north1"                              --repo jaakkokorhonen/froide-mcp
gh variable set GCP_PROJECT_ID  --body "your-gcp-project-id"                       --repo jaakkokorhonen/froide-mcp
gh variable set MCP_SERVICE_URL --body "https://froide-mcp-abcd1234-lm.a.run.app"  --repo jaakkokorhonen/froide-mcp
```

---

## Vaihe 7 — Manuaalinen deploy-testi

Ennen kuin luotetaan tagin triggeröimään `cd.yml`:ään, ajetaan workflow
kerran käsin `main`-haarasta. Tämä varmentaa WIF-autentikaation, Docker pushin
ja Cloud Run -deployn toimivuuden.

**GitHub → Actions → Deploy → Run workflow → Branch: main → Run workflow**

Seuraa lokit. Jos workflow epäonnistuu:

| Virhe | Todennäköinen syy |
|---|---|
| `Permission denied` WIF-vaiheessa | WIF-poolin `attribute_condition` tai SA-binding väärin |
| `denied: Permission` Docker pushissa | Deploy SA:lta puuttuu `roles/artifactregistry.writer` |
| `PERMISSION_DENIED` Cloud Run -vaiheessa | Deploy SA:lta puuttuu `roles/run.developer` tai `roles/iam.serviceAccountUser` |
| Smoke-testit skippautuvat | `MCP_SERVICE_URL`-variable puuttuu tai on tyhjä |
| Smoke-testit kaatuvat 401:een | `SMOKE_SESSION_TOKEN` vanhentunut tai puuttuu |

---

## Vaihe 8 — Smoke-token

```bash
# Avaa selaimessa
open https://froide-mcp-abcd1234-lm.a.run.app/auth/login

# Suorita Google-kirjautuminen.
# Palvelin palauttaa JSON-vastauksen:
#   {"session_token": "eyJ..."}

# Kopioi token ja aseta se secretiksi
gh secret set SMOKE_SESSION_TOKEN --repo jaakkokorhonen/froide-mcp
```

Aja workflow uudelleen manuaalisesti (vaihe 7) ja varmista, että smoke-testit
ajavat eikä yhtäkään testistä tule `SKIPPED`.

---

## Vaihe 9 — CHANGELOG.md päivitetään

Päivitä `CHANGELOG.md` ennen tagia:

```diff
-## [Unreleased] — v0.1.0
+## [v0.1.0] — 2026-06-30
```

Päivitä myös viimeinen rivi:

```diff
-[Unreleased]: https://github.com/jaakkokorhonen/froide-mcp/compare/HEAD...HEAD
+[v0.1.0]: https://github.com/jaakkokorhonen/froide-mcp/releases/tag/v0.1.0
```

Committaa muutos suoraan `main`-haaraan:

```bash
git add CHANGELOG.md
git commit -m "chore: release v0.1.0"
git push origin main
```

---

## Vaihe 10 — Tagi ja GitHub Release

```bash
git tag v0.1.0
git push origin v0.1.0
```

Tagi triggeröi `cd.yml`:n automaattisesti. Seuraa **Actions**-näkymässä, että
koko pipeline (Build → Push → Deploy → Smoke) menee vihreäksi.

Luo sen jälkeen GitHub Release:

```bash
gh release create v0.1.0 \
  --title "v0.1.0 — First deployable release" \
  --notes "$(sed -n '/^## \[v0.1.0\]/,/^## \[/p' CHANGELOG.md | head -n -1)"
```

Tai manuaalisesti: **GitHub → Releases → Draft a new release → Tag: v0.1.0**.

---

## Vaihe 11 — Varmistus

```bash
# Palvelu vastaa
curl https://froide-mcp-abcd1234-lm.a.run.app/healthz
# → {"status": "ok"}

# Autentikaatio toimii
curl -H "X-Froide-Session: <token>" \
  https://froide-mcp-abcd1234-lm.a.run.app/healthz

# Nightly monitoring käynnissä
# Actions → Nightly monitoring → kello 04:00 UTC (07:00 EEST)
```

---

## Yhteenveto — tarkistuslista

| # | Vaihe | Valmis |
|---|---|---|
| 1 | WIF-pool ja deploy SA luotu | ☐ |
| 2 | `terraform apply` × 2 (URL ensin, sitten `mcp_base_url`) | ☐ |
| 3 | Google OAuth2 Client luotu, redirect URI oikein | ☐ |
| 4 | Froide OAuth2 Application luotu | ☐ |
| 5 | Secret Manager -arvot täytetty | ☐ |
| 6 | GitHub Actions secretit ja variablet asetettu (5 kpl, ilman smoke-tokenia) | ☐ |
| 7 | Manuaalinen deploy-testi vihreänä Actions-näkymässä | ☐ |
| 8 | `SMOKE_SESSION_TOKEN` asetettu, smoke-testit ajavat (ei SKIPPED) | ☐ |
| 9 | `CHANGELOG.md` päivitetty (`[Unreleased]` → `[v0.1.0]`) | ☐ |
| 10 | `git tag v0.1.0 && git push origin v0.1.0` — pipeline vihreänä | ☐ |
| 11 | GitHub Release luotu, `/healthz` vastaa | ☐ |
