# Pipeline Garmin → BigQuery → MCP: especificación para Claude Code

Owner: el usuario (llamado **HUMANO** en este documento) · Builder: Claude Code · Runtime: GitHub Actions · Máquina: macOS

Este archivo es la fuente de verdad del build. El código del repo implementa todo lo descrito aquí. Claude: léelo completo antes de actuar, sigue las fases en orden y detente en cada **[STOP: HUMANO]**.

**Reglas de trabajo, siempre:**
- Pide permiso antes de **cualquier login**, de **crear recursos en la nube** y de **todo lo que toque credenciales**.
- Nunca pidas ni leas la contraseña de Garmin ni los client secrets de OAuth. El HUMANO los introduce él mismo.
- Nunca imprimas tokens ni secretos.
- No adivines nombres de campos del JSON de Garmin: inspecciona payloads reales antes de escribir cada vista.
- Al final de cada fase, da un resumen corto de estado.
- Este spec se basa en un build real (octubre 2026). La sección §14 lista los problemas que aparecieron y cómo se resolvieron; léela antes de empezar.

**Este repo ya trae el código completo y probado** (extract, load, vistas, workflow, bootstrap, regla MCP de solo lectura). Tu trabajo no es reescribirlo, sino:
1. **Configurar:** todos los valores de cada persona van en `project.env` (copiar de `project.env.example`). El código no tiene IDs fijos.
2. **Verificar contra los datos reales del HUMANO:** firmas de `garminconnect`, detección de días vacíos y rutas JSON de las vistas. Ajusta solo si algo difiere.
3. **Desplegar** fase por fase, con los STOP y los permisos de abajo.

Si actualizas `garminconnect` a una versión más nueva que la de `requirements.txt`, vuelve a verificar la auth (§5) antes de seguir.

Placeholders que se completan en P0 (y se guardan en `project.env`): `<PROJECT_ID>`, `<PROJECT_NUMBER>`, `<GH_USER>/<REPO>`, `<REPO_ID>`, `<USER_EMAIL>`, `<ORG_ID>` (si hay organización), `<TZ>` (por ejemplo `Europe/Madrid`) y los horarios de sync.

---

## 1. Decisiones fijas

| Área | Decisión |
|---|---|
| Fuente | Garmin Connect vía `python-garminconnect` (API no oficial). Verificar la versión instalada (ver §5) |
| Destino | BigQuery, región `EU` (o la que elija el HUMANO) |
| Sync | GitHub Actions, **3 veces al día a hora local del HUMANO** (por defecto 08:30, 15:07 y 21:07), correcto todo el año aunque cambie el horario de verano. Cada corrida re-trae los últimos 3 días |
| Alcance | Métricas diarias de salud, actividades (a nivel resumen), composición corporal |
| Fuera de alcance | Archivos FIT y tracks GPS, dashboards |
| Credenciales | Tokens de Garmin solamente (nunca la contraseña), guardados en **GCP Secret Manager** con escritura de los tokens renovados. **Sin claves de service account.** CI usa **Workload Identity Federation**, restringido a un repo y a `main`. Las corridas locales usan el ADC del HUMANO impersonando la service account |
| Acceso IA | **Servidor MCP gestionado por Google** (`https://bigquery.googleapis.com/mcp`), con OAuth como el HUMANO y una **deny policy de solo lectura** |

---

## 2. Arquitectura y principios

```
Garmin Connect API ──(garminconnect, tokens en Secret Manager)──► garmin_sync.py
   ├─ local: backfill / pruebas (ADC impersonando la SA)
   └─ GitHub Actions 3×/día (WIF, sin claves)
        │ JSON crudo → tabla staging → MERGE
        ▼
BigQuery: garmin_raw (JSON por endpoint)  →  garmin (vistas limpias con descripciones)
        ▼
MCP de BigQuery (Google) ──OAuth──► Claude (custom connector) y ChatGPT (custom MCP server)
```

Principios:
- **Raw first.** Guardar el JSON intacto y parsearlo en vistas SQL.
- **Idempotente.** Re-correr cualquier rango nunca crea duplicados.
- **Incremental.** Cada corrida re-trae los últimos 3 días, porque Garmin rellena datos tarde.
- **Determinista.** No hay IA en el runtime.

---

## 3. Fase P0: prerrequisitos [STOP: HUMANO]

Verifica cada punto antes de seguir.

| # | Tarea (la hace el HUMANO) | Verificación (Claude) |
|---|---|---|
| 1 | `brew install python@3.12 gh git` + `brew install --cask google-cloud-sdk` | `python3.12 --version`, `gh --version`, `gcloud --version`. gcloud puede no estar en el PATH: busca en `~/google-cloud-sdk/bin` |
| 2 | `gh auth login` | `gh auth status` |
| 3 | `gcloud auth login` | `gcloud auth list` |
| 4 | Crear el proyecto | `gcloud projects describe <PROJECT_ID>` (anota `projectNumber` y `parent`; si es una organización, anota `<ORG_ID>`) |
| 5 | Facturación + alerta de presupuesto de 5 €/mes | `gcloud billing projects describe <PROJECT_ID>` → `billingEnabled: True` |
| 6 | BigQuery API | `gcloud services list --enabled` incluye `bigquery.googleapis.com` (si no, pide permiso para habilitarla) |
| 7 | Datos del HUMANO | Confirmar `<GH_USER>/<REPO>`, `<USER_EMAIL>`, `<TZ>`, los horarios de sync y desde qué fecha hacer el backfill |

Anota los valores en la sección "Valores del proyecto", al final de este archivo.

---

## 4. Estructura del repo

```
garmin-pipeline/
├── CLAUDE.md, README.md
├── requirements.txt              # pip freeze completo (pinned)
├── .gitignore                    # tokens, *credentials*.json, gha-creds-*.json, .env, .venv, state/
├── garmin_sync.py                # CLI
├── src/{config,auth,extract,load}.py
├── sql/00_create_raw_tables.sql
├── sql/views/01_daily_health.sql … 06_daily_overview.sql
├── sql/views/descriptions.json   # descripciones de datasets, vistas y columnas (para MCP)
├── scripts/bootstrap_gcp.sh      # idempotente: todo el setup de GCP
├── scripts/export_tokens.sh      # sube los tokens locales de Garmin a Secret Manager
├── scripts/mcp_readonly_deny_policy.json
├── state/                        # checkpoint del backfill (gitignored)
└── .github/workflows/daily-sync.yml
```

Fase **P1 (repo desde la plantilla):**
1. Crear el repo **privado** del HUMANO a partir de esta plantilla: `gh repo create <GH_USER>/<REPO> --private --template santicura86/garmin-bigquery-mcp --clone` (o "Use this template" en GitHub), y trabajar dentro de ese clon.
2. `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. `cp project.env.example project.env` y completarlo. `GITHUB_REPO_ID` sale de `gh api repos/<GH_USER>/<REPO> --jq .id`.
4. Si `<TZ>` no es Europe/Madrid o los horarios son otros, ajustar los crons y los offsets del `gate` en `daily-sync.yml` (ver §8).
5. Commit y push de `project.env`: no tiene secretos, pero el repo debe ser privado.

---

## 5. Garmin: endpoints y auth

**Antes de escribir `extract.py`**, verifica las firmas con `inspect.signature` y lee `garminconnect/client.py`. La auth cambió en la versión 0.3.x y puede volver a cambiar. Si algo difiere de lo descrito aquí, avisa al HUMANO.

Lo verificado en `garminconnect==0.3.17`:
- **Ya no usa `garth`.** Los tokens se guardan en un único `garmin_tokens.json` dentro del directorio de tokens: un DI access token (JWT, ~30 h de vida) y un refresh token opaco. La librería renueva el token cuando faltan 15 min para que expire y **puede rotar el refresh token**.
- **Login interactivo:** `Garmin(email, password, prompt_mfa=...).login(token_dir)`.
- **Restore solo con tokens:** `Garmin().login(token_dir)`, sin email ni contraseña, así la librería no puede caer en un login con contraseña.

**Diseño de tokens (obligatorio):**
- Secret Manager (`garmin-tokens`) es la fuente de verdad.
- Cada corrida lee la última versión, la escribe en `GARMIN_TOKEN_DIR`, hace login solo con tokens y, si `api.client.dumps()` cambió (comparando el JSON *parseado*, no el texto), guarda una nueva versión.
- Tras guardar: la versión nueva queda habilitada, las 2 anteriores deshabilitadas y las más viejas destruidas. Las versiones deshabilitadas también cuentan para la facturación; así se mantiene dentro de las 6 gratuitas.
- Si los tokens son rechazados, falla con: "Garmin tokens expired — run `python garmin_sync.py login` and `scripts/export_tokens.sh` locally, then re-run the workflow."
- Mapea `GarminConnectAuthenticationError`, también a mitad de una corrida, a ese mismo mensaje.

| Tabla raw | Método | Grano | record_id | Notas verificadas |
|---|---|---|---|---|
| `raw_daily_summary` | `get_user_summary(d)` | día | fecha | |
| `raw_sleep` | `get_sleep_data(d)` | día | fecha | Vacío salvo que `dailySleepDTO.sleepTimeSeconds` o `sleepStartTimestampGMT` tengan valor (ver §14) |
| `raw_hrv` | `get_hrv_data(d)` | día | fecha | Vacío si no hay `hrvSummary` |
| `raw_stress` | `get_stress_data(d)` | día | fecha | |
| `raw_body_battery` | `get_body_battery(d, d)` | día | fecha | Devuelve una lista de 1 elemento: guardar el elemento |
| `raw_heart_rate` | `get_heart_rates(d)` | día | fecha | |
| `raw_respiration` | `get_respiration_data(d)` | día | fecha | |
| `raw_spo2` | `get_spo2_data(d)` | día | fecha | |
| `raw_training_readiness` | `get_training_readiness(d)` | día | fecha | Lista de snapshots del día: guardar la lista |
| `raw_activities` | `get_activities_by_date(start, end)` | actividad | `activityId` | `date` = `startTimeLocal[:10]` |
| `raw_body_composition` | `get_body_composition(start, end)` | día | fecha | Agrupar `dateWeightList` por `calendarDate`. El peso viene en **gramos** |

**Días vacíos:** Garmin devuelve un esqueleto con campos de metadata (`calendarDate`, `userProfilePK`, etc.) aunque no haya datos. Considera "vacío" cuando no hay ningún valor no nulo fuera de las claves de metadata. Deriva esas claves de una respuesta real de un día sin datos (por ejemplo 2005-01-01). Los días vacíos se saltan con un log INFO, no son errores.

**Errores:** si un endpoint falla, el resto sigue. Junta los errores y sale con código distinto de cero al final.

**Throttle:** ~1 request/s. Ante un 429 (`GarminConnectTooManyRequestsError`), backoff exponencial con un máximo de 5 reintentos.

---

## 6. BigQuery

### 6.1 Bootstrap (`scripts/bootstrap_gcp.sh`, idempotente, lee `project.env`)

Ya implementado. Muéstrale al HUMANO lo que va a crear y pide permiso antes de correrlo. Puede requerir re-correrlo (ver §14.3). Lo que hace:
- **Datasets** `garmin_raw` y `garmin`, en la ubicación elegida.
- **Service account** `garmin-sync@<PROJECT_ID>.iam.gserviceaccount.com`:
  - `roles/bigquery.jobUser` a nivel proyecto.
  - `roles/bigquery.dataEditor` **a nivel dataset**, mediante SQL:
    ```sql
    GRANT `roles/bigquery.dataEditor` ON SCHEMA `<PROJECT_ID>.<ds>` TO "serviceAccount:<SA>"
    ```
    No uses `bq add-iam-policy-binding`: para datasets exige un allowlist.
- **Sin claves de service account**, aunque la organización las permita.
- **Para el HUMANO:** `roles/iam.serviceAccountTokenCreator` sobre la SA, para correr en local con impersonación.
- **APIs:** `iamcredentials.googleapis.com`, `sts.googleapis.com`, `secretmanager.googleapis.com`.
- **WIF:**
  - Pool `github` y provider OIDC `github-actions`, con issuer `https://token.actions.githubusercontent.com`.
  - Mapping: `google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref`.
  - Condición: `assertion.repository_id=='<REPO_ID>' && assertion.repository=='<GH_USER>/<REPO>' && assertion.ref=='refs/heads/main'`.
  - Binding `roles/iam.workloadIdentityUser` a `principalSet://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/attribute.repository/<GH_USER>/<REPO>`.
- **Secret Manager:** `garmin-tokens`, con replicación user-managed en una región de la misma zona que los datos (por ejemplo `europe-west1`). A la SA le das `secretAccessor` y `secretVersionManager` **solo sobre ese secreto**.
- **Descripciones de datasets** (`bq update --description`) desde `descriptions.json`. Se ejecutan como owner, porque la SA no tiene `bigquery.datasets.update`.
- **MCP:** ver la fase P10.

Exit P2: `bq ls` muestra los dos datasets. Después de que el HUMANO corra `gcloud auth application-default login --impersonate-service-account=<SA>`, el cliente Python lista los datasets, corre un query y crea y borra una tabla de prueba en cada dataset.

### 6.2 Tablas raw (todas iguales)
`date DATE NOT NULL, record_id STRING NOT NULL, payload JSON, ingested_at TIMESTAMP NOT NULL, source_version STRING`, con `PARTITION BY date CLUSTER BY record_id`. Créalas con `CREATE TABLE IF NOT EXISTS` al inicio de cada corrida.

### 6.3 Carga
1. Deduplicar por `record_id` en Python.
2. `load_table_from_json` a una staging `_stg_<tabla>_<uuid>` (`WRITE_TRUNCATE`), con `payload` como **STRING**.
3. `MERGE` sobre `record_id`, usando `PARSE_JSON(payload, wide_number_mode => 'round')` (con el modo por defecto `exact` fallan algunos floats).
4. Borrar la staging en `finally`.

### 6.4 Vistas (`garmin`)
Inspecciona payloads reales primero. Las rutas siguientes salieron del build real; confírmalas igual. Usa `LAX_INT64` / `LAX_FLOAT64` / `LAX_STRING`.

- **`daily_health`:**
  - `totalSteps`, `totalDistanceMeters/1000`, `restingHeartRate`, `min/maxHeartRate`.
  - `averageStressLevel` y `maxStressLevel`: **un valor negativo significa "datos insuficientes" y se convierte en NULL**.
  - `bodyBatteryHighestValue/LowestValue/ChargedValue/DrainedValue`, `activeKilocalories`, `totalKilocalories`.
  - `moderateIntensityMinutes`, `vigorousIntensityMinutes`; `intensity_minutes = moderate + 2×vigorous` (convención de Garmin).
  - `floorsAscended`, `avgWakingRespirationValue`, `averageSpo2`.
- **`sleep`:**
  - Todo bajo `dailySleepDTO`.
  - Los timestamps `*Local` son epoch ms del reloj local: se convierten con `DATETIME(TIMESTAMP_MILLIS(x))`. Los `*GMT` son UTC reales.
  - `sleepTimeSeconds`, `deep/light/rem/awakeSleepSeconds`, en minutos.
  - `sleepScores.overall.value` y `.qualifierKey`.
- **`hrv`:** `hrvSummary.weeklyAvg`, `lastNightAvg`, `lastNight5MinHigh`, `status`.
- **`activities`:**
  - `activityId`, `PARSE_DATETIME('%Y-%m-%d %H:%M:%S', startTimeLocal)`, `activityType.typeKey`, `activityName`.
  - `duration/60` (tiempo total transcurrido), `movingDuration/60`, `distance/1000`.
  - `averageHR`, `maxHR`, `calories`, `elevationGain`, `aerobic/anaerobicTrainingEffect`, `trainingEffectLabel`.
- **`body_composition`:**
  - `UNNEST(JSON_QUERY_ARRAY(payload))`, quedándote con el último pesaje del día.
  - `weight/1000`, `muscleMass/1000`, `boneMass/1000`; `bmi`, `bodyFat`, `bodyWater` en %.
- **`daily_overview`:**
  - Un *spine* de fechas: la unión de todas las vistas.
  - LEFT JOIN de `daily_health`, `sleep`, `hrv` y `body_composition`.
  - Agregado diario de actividades: `activity_count`, `activity_min`, `activity_distance_km`, `activity_kcal`, `activity_types`.

**Descripciones (clave para que MCP funcione bien):**
- `descriptions.json` tiene la descripción de cada dataset, de cada vista y de **cada columna, con su unidad**.
- `daily_overview` se marca como "MAIN TABLE … use this first".
- `garmin_sync.py views` crea las vistas y después aplica las descripciones de vistas y columnas (`update_table`, campo `schema`). Hay que hacerlo después de cada deploy, porque `CREATE OR REPLACE VIEW` las borra.

---

## 7. CLI (`garmin_sync.py`)

| Comando | Comportamiento |
|---|---|
| `login` | Login interactivo con MFA (pide email, `getpass` y código); guarda los tokens en `~/.garminconnect`. **Lo corre el HUMANO en su terminal** |
| `sync [--days N] [--only a,b] [--dry-run]` | Por defecto, los últimos 3 días: `[hoy-(N-1), hoy]` |
| `backfill --start --end [--only] [--dry-run]` | Por meses, con checkpoint en `state/checkpoint.json` después de cada mes. Reanudable. Si un mes falla, se detiene y no avanza el checkpoint |
| `views` | Despliega las vistas y aplica las descripciones |

`scripts/export_tokens.sh` sube `~/.garminconnect/garmin_tokens.json` a Secret Manager (usa la misma lógica de rotación) sin imprimir el contenido.

---

## 8. GitHub Actions (`.github/workflows/daily-sync.yml`)

- **Triggers:** `schedule` + `workflow_dispatch` (input `days`, por defecto 3).
- **Horarios locales con cambio de horario:** el cron de GitHub va solo en UTC.
  - Por cada hora local, programa **dos** crons: uno para el offset de verano y otro para el de invierno.
  - Un job `gate` compara el cron que disparó (`github.event.schedule`) con el offset actual (`TZ=<TZ> date +%z`) y solo deja pasar el que corresponde. Funciona aunque GitHub retrase la corrida.
  - Ejemplo para Europe/Madrid (08:30, 15:07, 21:07): `30 6`/`30 7`, `7 13`/`7 14`, `7 19`/`7 20`.
  - Usa minutos como :07 o :30, no :00, porque GitHub retrasa más las horas en punto.
  - **Simula la lógica del gate** con fechas de verano y de invierno antes de hacer push.
- **Jobs:**
  - `gate`: sin permisos especiales.
  - `sync`:
    - `needs: gate`, `if: needs.gate.outputs.run == 'true'`.
    - **concurrency a nivel job** (`group: garmin-sync`, `cancel-in-progress: false`), para que los gates descartados no desplacen un sync pendiente.
    - Permisos `contents: read`, `id-token: write`.
  - `keepalive`:
    - Solo en `schedule`, cuando el gate pasa.
    - Permiso `actions: write`.
    - Corre `gh api -X PUT repos/<repo>/actions/workflows/daily-sync.yml/enable`, que reinicia el contador de 60 días de inactividad sin hacer commits.
- **Pasos de `sync`:**
  1. Fija `GARMIN_TOKEN_DIR` con `echo "GARMIN_TOKEN_DIR=$RUNNER_TEMP/garmin-tokens" >> "$GITHUB_ENV"`. No se puede usar `${{ runner.temp }}` en el `env` del job.
  2. `actions/checkout` (`persist-credentials: false`).
  3. `google-github-actions/auth` (`workload_identity_provider` + `service_account`).
  4. `actions/setup-python` (3.12, cache pip).
  5. `pip install -r requirements.txt`.
  6. `python garmin_sync.py sync --days "$DAYS"`.
  7. `if: always()`: borrar el directorio de tokens y el archivo de credenciales.
- **Fija cada action a un commit SHA** de un release con al menos 2 semanas de antigüedad.
- **Variables del repo** (`gh variable set`, no secretas): `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER` (`projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github-actions`), `GCP_SERVICE_ACCOUNT` y `SYNC_TZ`. **No hay GitHub Secrets.**

Exit P8: una corrida manual con `workflow_dispatch` en `main` termina en verde.

---

## 9. Fases

| Fase | Salida | Criterio de salida |
|---|---|---|
| **P0** Prerrequisitos | §3 | Todo verificado **[STOP: HUMANO]** |
| **P1** Repo | Repo privado creado desde la plantilla, `project.env` completo, crons ajustados | `git push` funciona; ningún secreto trackeado |
| **P2** Bootstrap GCP | §6.1 sin MCP (WIF después de P1, porque necesita `<REPO_ID>`) | Datasets OK; ADC impersonado lee, escribe y consulta |
| **P3** Auth Garmin | `login` + Secret Manager + `export_tokens.sh` | El HUMANO completa el MFA **[STOP: HUMANO]**; el restore desde Secret Manager funciona |
| **P4** Extract + load | `sync --days 7 --dry-run` y después una corrida real | Filas en las tablas raw con datos; 0 duplicados; sin tablas staging sobrantes |
| **P5** Backfill | Desde la fecha que eligió el HUMANO (correr en background con `caffeinate -i`) | Checkpoint en hoy; conteos por tabla; días faltantes listados |
| **P6** Vistas | §6.4 + descripciones | Cada vista devuelve filas; ninguna columna sin descripción |
| **P7** Validación | 3 fechas al azar + ayer: pasos, FC en reposo, sueño, HRV, última actividad (distancia y duración total), último peso | El HUMANO confirma que coinciden con la app **[STOP: HUMANO]**. También: `sync --days 3` corrido dos veces no deja duplicados, y `git log -p` no contiene credenciales |
| **P8** Automatización | §8 | Corrida manual en verde |
| **P9** Docs | README con un runbook (re-login de Garmin, gaps, auth vencida, workflow pausado) | El HUMANO puede re-autenticarse usando solo el README |
| **P10** MCP | §10 | Herramientas read-only OK y `execute_sql` denegado; Claude y ChatGPT conectados **[STOP: HUMANO]** |

---

## 10. Fase P10: MCP de BigQuery para Claude y ChatGPT

El servidor `https://bigquery.googleapis.com/mcp` es de Google y se habilita junto con la BigQuery API; no hay nada que hostear. Usa OAuth y actúa con la identidad del HUMANO, sobre la que se evalúan los permisos IAM. Herramientas: `list_dataset_ids`, `list_table_ids`, `get_dataset_info`, `get_table_info`, `execute_sql_readonly`, `get_query_results` y `get_job` son read-only; **`execute_sql` y `cancel_job` no lo son**. Límites: 3.000 filas y 3 min por query.

Pasos de Claude (con permiso del HUMANO):
1. **Rol de acceso:** `gcloud projects add-iam-policy-binding <PROJECT_ID> --member user:<USER_EMAIL> --role roles/mcp.toolUser`.
2. **Deny policy de solo lectura.** Crear `scripts/mcp_readonly_deny_policy.json`:
   ```json
   {
     "displayName": "MCP read-only",
     "rules": [{
       "denyRule": {
         "deniedPrincipals": ["principalSet://goog/public:all"],
         "deniedPermissions": ["mcp.googleapis.com/tools.call"],
         "denialCondition": {
           "title": "Deny read-write MCP tools",
           "expression": "api.getAttribute('mcp.googleapis.com/tool.isReadOnly', false) == false"
         }
       }
     }]
   }
   ```
   Luego: `gcloud iam policies create mcp-read-only --attachment-point=cloudresourcemanager.googleapis.com/projects/<PROJECT_ID> --kind=denypolicies --policy-file=...`.
   - El rol Owner **no** alcanza: hace falta `roles/iam.denyAdmin`.
   - Si hay organización, el HUMANO se lo otorga él mismo; **Claude no modifica IAM de la organización**:
     `gcloud organizations add-iam-policy-binding <ORG_ID> --member=user:<USER_EMAIL> --role=roles/iam.denyAdmin --condition=None`.
   - Sin organización (Gmail personal): investiga en la documentación actual cómo crear deny policies a nivel proyecto y explícale las opciones al HUMANO antes de seguir.
3. **Verificación con curl** (token de `gcloud auth print-access-token`, header `x-goog-user-project: <PROJECT_ID>`, POST JSON-RPC al endpoint):
   - `tools/list` lista las herramientas con su `readOnlyHint`.
   - `tools/call execute_sql_readonly` con un SELECT sobre `garmin.daily_overview` → **OK**.
   - `tools/call execute_sql` con `SELECT 1` → **"Access Denied … mcp.tools.call"**.
4. **Guiar al HUMANO** (él maneja los secretos):
   - **Pantalla de consentimiento** en Google Auth Platform: Internal si es Workspace; si es Gmail, External en modo prueba agregándose como test user.
   - **Dos OAuth clients** de tipo Web application, con la casilla **"Use this client for an AI-powered agent"** marcada:
     - Claude: origin `https://claude.ai`, redirect `https://claude.ai/api/mcp/auth_callback`.
     - ChatGPT: redirect `https://chatgpt.com/connector_platform_oauth_redirect`; si ChatGPT muestra otra callback URL, agregarla también.
   - **Claude:** Settings → Connectors → Add custom connector, con la URL del endpoint y el Client ID y secret en "Advanced settings".
   - **ChatGPT (Business):** activar Developer mode y luego **Add custom MCP server**, con la URL, OAuth y el Client ID y secret del cliente de ChatGPT.
   - **Prueba final:** consultar `garmin.daily_overview` de los últimos 14 días desde cada asistente.
5. Agregar el paso 1, la deny policy y las descripciones de datasets a `bootstrap_gcp.sh`, para poder reconstruir todo.

---

## 11. Runbook (para el README)

| Situación | Acción |
|---|---|
| "Garmin tokens expired" | `python garmin_sync.py login` → `scripts/export_tokens.sh` → re-correr el workflow |
| Otro fallo del sync | Revisar el log de Actions; re-correr con `workflow_dispatch`; si Garmin cambió algo, actualizar `garminconnect`, probar con `--dry-run` y hacer push |
| Hueco en los datos | `backfill --start X --end Y` |
| Falla la auth de GCP en Actions | Revisar que corrió en `main` y las variables del repo; si el repo cambió de nombre, actualizar la condición WIF y el `principalSet` |
| ADC local vencido | `gcloud auth application-default login --impersonate-service-account=<SA>` |
| Un conector MCP pide reconectar | Volver a hacer login de Google en el conector |

---

## 12. Riesgos

| Riesgo | Mitigación |
|---|---|
| Cambios en la API o auth no oficial de Garmin | Versiones pinned, JSON crudo, mensajes de error claros |
| Rotación del refresh token | Escritura de tokens renovados en Secret Manager en cada corrida |
| GitHub pausa los schedules tras 60 días | Job keepalive |
| GitHub retrasa los schedules (3–5 h observado) | Aceptado: cada corrida re-trae 3 días. Si hace falta puntualidad, Cloud Scheduler con TZ y un Cloud Run Job con la SA |
| La IA modifica datos | Deny policy de solo lectura, verificada |
| Fuga de credenciales | Sin claves GCP, WIF restringido a repo y `main`, la SA solo accede a 2 datasets, tokens de Garmin en Secret Manager, sin GitHub Secrets |
| Privacidad | Los resultados de cada query van al proveedor de IA; el HUMANO lo sabe y lo acepta |

---

## 13. Costos esperados
~0 €. BigQuery queda en la capa gratuita (10 GB de almacenamiento y 1 TB de consultas por mes); Secret Manager tiene 6 versiones y 10k accesos gratis; GitHub Actions usa unos 400 min/mes de los 2.000 gratis para repos privados. Igual conviene tener la alerta de presupuesto de 5 €.

---

## 14. Problemas encontrados en el build original (léelos antes de empezar)

1. **Organización con `iam.managed.disableServiceAccountKeyCreation`:** la creación de claves está bloqueada. Por eso el diseño ya es sin claves (WIF + impersonación). Un `keys create` fallido puede dejar un archivo vacío de 0 bytes: bórralo.
2. **`bq add-iam-policy-binding` en datasets** → "requires allowlisting". Usa `GRANT … ON SCHEMA`.
3. **WIF recién creado** → `PERMISSION_DENIED` al agregar el binding `principalSet`: es propagación, re-correr el script.
4. **WIF en Actions** falla con "IAM Service Account Credentials API has not been used" → habilita `iamcredentials.googleapis.com` (y `sts`).
5. **`${{ runner.temp }}` en el `env` del job** → error de parseo del workflow. Usa `$RUNNER_TEMP` en un step.
6. **Sueño con falsos positivos:** `dailySleepDTO` siempre trae `sleepNeed` y `nextSleepNeed` (recomendaciones calculadas), aunque no se haya dormido con el reloj. Exige `sleepTimeSeconds` o `sleepStartTimestampGMT`.
7. **Días vacíos** devuelven esqueletos con metadata, no `null`. Ver §5.
8. **Unidades:** el peso y las masas vienen en gramos; duraciones en segundos; distancias en metros; el estrés negativo significa sin datos.
9. **La SA no puede editar la descripción de los datasets** (`bigquery.datasets.update`): hazlo como owner en el bootstrap.
10. **Deny policy:** Owner no alcanza, hace falta `roles/iam.denyAdmin`. El JSON del ejemplo de Google tiene una coma final que lo vuelve inválido: usa el de §10.
11. **Google Workspace exige reautenticarse periódicamente:** `gcloud` y el ADC vencen ("Reauthentication is needed"). Al HUMANO le pides que re-corra el login; CI no se ve afectado. Verifica el ADC con una llamada real a la API, no solo leyendo el email.
12. **Cron de GitHub:** retrasos de horas y solo UTC. Usa el patrón de gate de §8.
13. **git del sistema muy viejo** (por ejemplo 2.6): sin `git init -b`. Usa `git symbolic-ref HEAD refs/heads/main`.
14. **El usuario puede no tener datos de sueño, HRV o peso** (no usa el reloj de noche, no tiene balanza). Es normal: las tablas quedan vacías hasta que existan esos datos. No lo trates como un error.

---

## Valores del proyecto (completar en P0)
- `<PROJECT_ID>`: ______ · `<PROJECT_NUMBER>`: ______ · `<ORG_ID>`: ______
- `<GH_USER>/<REPO>`: ______ · `<REPO_ID>`: ______
- `<USER_EMAIL>`: ______ · `<TZ>`: ______ · horarios de sync: ______
- Backfill desde: ______
