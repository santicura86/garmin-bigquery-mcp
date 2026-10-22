# Garmin → BigQuery → Claude y ChatGPT: guía para vos (la parte humana)

Esta guía explica qué vas a construir y por qué, y qué pasos tenés que hacer vos con tus manos. Todo lo técnico lo hace Claude Code, usando el repo plantilla (código ya probado) y su `CLAUDE.md`.

---

## 1. Qué vas a tener al final

```
Reloj / balanza Garmin
      │  (se sincroniza con la app Garmin Connect, como siempre)
      ▼
Garmin Connect
      │  un script lo lee 3 veces al día (GitHub Actions, gratis)
      ▼
BigQuery (tu base de datos en Google Cloud)
  ├── garmin_raw : los datos tal cual los da Garmin (copia de seguridad)
  └── garmin     : tablas limpias: pasos, FC, estrés, sueño, HRV, actividades, peso
      │  servidor MCP oficial de Google (solo lectura)
      ▼
Claude y ChatGPT: les preguntás en lenguaje natural y consultan tus datos reales
```

Ejemplos de preguntas que vas a poder hacer:
- "¿Cómo evolucionó mi FC en reposo los últimos 6 meses y cómo se relaciona con mi volumen de running?"
- "¿Qué días duermo peor? ¿Coincide con días de entrenamiento intenso?"
- "Comparame octubre de este año con el anterior en km, horas de entrenamiento y estrés medio."

---

## 2. Qué hace BigQuery acá

BigQuery es una base de datos de Google pensada para analizar datos. En este proyecto:

- **Guarda tu historial completo.** Una fila por día con decenas de métricas, más una fila por actividad. Para uso personal el volumen es mínimo, así que entra en la capa gratuita (cuesta ~0 €).
- **Se actualiza solo.** Un script corre 3 veces al día en GitHub, trae los últimos 3 días de Garmin y los mezcla sin duplicar nada. Volver a traer días ya cargados no crea duplicados: el script actualiza las filas que ya existen.
- **Guarda los datos en dos capas.**
  - `garmin_raw` es el JSON original de Garmin. Si Garmin cambia algo, no se pierde nada.
  - `garmin` son "vistas" que convierten ese JSON en columnas claras (`steps`, `resting_hr`, `sleep_score`, `distance_km`…), con descripción y unidades en cada columna para que la IA entienda qué es cada cosa.
- **Calcula, no solo almacena.** Cuando Claude o ChatGPT necesitan un promedio, una tendencia o una comparación, escriben una consulta SQL, BigQuery hace la cuenta exacta y devuelve solo el resultado.

---

## 3. Base de datos + MCP vs. datos en instrucciones o archivos .md

Hay dos formas de darle "tus datos" a una IA:

**A) Contexto estático:** pegás o exportás tus datos en las instrucciones del proyecto, en archivos `.md` o en un CSV adjunto.

**B) Base de datos + MCP:** la IA tiene una herramienta (MCP) para consultar la base de datos cuando la necesita.

| | A) Instrucciones / .md / CSV | B) BigQuery + MCP |
|---|---|---|
| **Actualización** | Manual: cada vez exportás y volvés a subir | Automática, 3 veces al día |
| **Cuánto historial entra** | Limitado por la ventana de contexto. 2 años × ~45 métricas son del orden de 100.000 tokens: ocupa casi todo el contexto o directamente no entra | Ilimitado en la práctica: la IA solo recibe el resultado de la consulta (unas pocas filas) |
| **Precisión de los cálculos** | La IA "lee" cientos de filas y calcula de cabeza, y en promedios o tendencias largas se equivoca con facilidad | Los calcula BigQuery con SQL, así que son exactos y reproducibles |
| **Costo y velocidad por pregunta** | Cada conversación carga todo el archivo | Solo viaja lo necesario |
| **Una sola fuente** | Cada herramienta tiene su copia, que se desactualiza | Claude, ChatGPT (y si querés un dashboard) leen la misma base |
| **Esfuerzo inicial** | Ninguno | Un par de horas, una sola vez (esta guía) |
| **Privacidad** | El archivo entero queda en la conversación | Solo los resultados de cada consulta van a la IA. Igual son datos de salud: tenelo en cuenta |
| **Riesgo de que la IA rompa algo** | Ninguno | Se elimina con una regla de **solo lectura**: la IA puede consultar, nunca borrar ni modificar |

**La combinación ideal:** en las instrucciones o en `.md` poné lo que es estable y cualitativo, como tus objetivos, tu plan de entrenamiento, lesiones o cómo querés que te hable. En la base de datos va todo lo que es número y cambia cada día. Así la IA tiene el *contexto* desde las instrucciones y los *hechos* desde BigQuery.

---

## 4. Qué necesitás antes de empezar

| Requisito | Notas |
|---|---|
| Mac, con Claude Code instalado | Los comandos de la guía son para macOS |
| Cuenta de Garmin Connect | Email y contraseña, y el teléfono a mano si tenés verificación en dos pasos |
| Cuenta de GitHub | Gratis. El repo va a ser privado |
| Cuenta de Google con **facturación activada** en Google Cloud | Hace falta una tarjeta. El uso es ~0 €; ponemos una alerta de presupuesto de 5 € por si acaso |
| **Claude Pro, Max, Team o Enterprise** | Para agregar un conector personalizado |
| **ChatGPT Business** (u otro plan con "Developer mode") | La documentación de Google pide Business para sus servidores MCP |

**Google Workspace o Gmail personal:** si tu correo es de un dominio propio (Google Workspace), todo es más simple, porque podés marcar el acceso como "Internal" y solo tu dominio puede entrar. Con un Gmail personal también funciona, pero la pantalla de consentimiento va como "External" en modo prueba, agregándote como usuario de prueba. Claude Code te va a guiar en ese caso.

---

## 5. Tus pasos, en orden

Claude Code te va a ir pidiendo cada uno en el momento justo. Esta lista es para que sepas qué viene.

### Antes de abrir Claude Code
1. **Instalá las herramientas** (en Terminal):
   ```bash
   brew install python@3.12 gh git
   brew install --cask google-cloud-sdk
   ```
2. **Iniciá sesión en GitHub:** `gh auth login` (HTTPS y navegador).
3. **Iniciá sesión en Google Cloud:** `gcloud auth login`
4. **Creá un proyecto en Google Cloud** (por ejemplo `garmin-data-tunombre`) desde console.cloud.google.com, y **vinculale la facturación** (Billing → Link a billing account).
5. **Creá una alerta de presupuesto** de 5 €/mes (Billing → Budgets & alerts).
6. **Creá tu propio repo privado desde la plantilla.** Abrí https://github.com/santicura86/garmin-bigquery-mcp y entrá en **Use this template** → **Create a new repository** (marcalo **Private**). Después clonalo en tu Mac y abrí Claude Code en esa carpeta.
   - Si no ves "Use this template", pedile a Claude Code que lo haga por vos con `gh repo create … --template …`. El link de la plantilla es `santicura86/garmin-bigquery-mcp`.
7. Pegale a Claude Code:
   > Lee CLAUDE.md. Es la especificación de mi pipeline Garmin → BigQuery → MCP, y el código de este repo ya la implementa. Empieza por la fase P0, sigue las fases en orden, detente en cada [STOP: HUMANO] y pídeme permiso antes de cualquier login, de crear recursos en la nube o de tocar credenciales. Dame un resumen corto al final de cada fase.

### Durante el build (te lo pide Claude Code)
8. **Confirmar nombres:** ID del proyecto, nombre del repo, tu zona horaria y a qué horas querés las sincronizaciones.
9. **Login de Google para el código local.** Claude te da el comando exacto:
   ```bash
   gcloud auth application-default login --impersonate-service-account=garmin-sync@TU-PROYECTO.iam.gserviceaccount.com
   ```
10. **Login de Garmin con verificación en dos pasos.** Lo corrés **vos** en tu Terminal (Claude te da el comando). Tu contraseña va solo a Garmin; Claude nunca la ve.
11. **Elegir desde cuándo cargar el historial** (por ejemplo, los últimos 2 años). La carga tarda ~1 h por año de datos y corre sola.
12. **Validar los números:** Claude te muestra pasos, FC en reposo y actividades de 3–4 días, y vos los comparás con la app de Garmin.
13. **Notificaciones de GitHub:** Settings → Notifications → Actions, activá el email para "failed workflows", así te enterás si algo falla.

### La parte MCP (conectar Claude y ChatGPT)
14. **Permiso para la regla de solo lectura.** Si usás Workspace, corré el comando que te da Claude para darte el rol "Deny Admin" en tu organización. Es lo que permite crear la regla que impide a la IA modificar datos.
15. **Pantalla de consentimiento.** En Google Cloud Console, entrá a Google Auth Platform → Branding → Get started:
    - Nombre de la app: lo que quieras, por ejemplo "Garmin BigQuery MCP".
    - Email de soporte: el tuyo.
    - Audience: **Internal** (Workspace) o **External** con vos como usuario de prueba (Gmail).
16. **Dos "OAuth clients".** En Google Auth Platform → Clients → Create client, tipo **Web application**, marcando la casilla **"Use this client for an AI-powered agent"**:

    | Cliente | Authorized JavaScript origin | Authorized redirect URI |
    |---|---|---|
    | Claude | `https://claude.ai` | `https://claude.ai/api/mcp/auth_callback` |
    | ChatGPT | (vacío) | `https://chatgpt.com/connector_platform_oauth_redirect` |

    Guardá cada **Client ID** y **Client secret** en un gestor de contraseñas. Google muestra el secret una sola vez. **No se lo pegues a Claude Code**: va directo a Claude y ChatGPT.
17. **Conector en Claude:** claude.ai → Settings → Connectors → **Add custom connector**.
    - URL: `https://bigquery.googleapis.com/mcp`
    - En "Advanced settings" pegá el Client ID y el secret del cliente de Claude.
    - Iniciá sesión con tu cuenta de Google.
18. **Conector en ChatGPT:** activá Developer mode (Settings → Apps & Connectors → Advanced). Después andá a **Add custom MCP server**:
    - URL: `https://bigquery.googleapis.com/mcp`
    - Auth: **OAuth**, con el Client ID y el secret del cliente de ChatGPT.
    - Si el formulario muestra una "Callback URL" distinta de la que pusiste en Google, agregala también como redirect URI en el cliente de Google.
19. **Probalo:**
    > Usando el proyecto de BigQuery `TU-PROYECTO`, consulta `garmin.daily_overview` de los últimos 14 días: fecha, pasos, FC en reposo, estrés medio y tipos de actividad.

---

## 6. Cosas que conviene saber

- **La regla de solo lectura funciona así:** la IA tiene dos herramientas SQL. `execute_sql_readonly` está permitida; `execute_sql` está bloqueada. Si la IA intenta la segunda y recibe "Access Denied", es la regla haciendo su trabajo: pedile que use `execute_sql_readonly`.
- **GitHub retrasa los horarios programados**, a veces de 3 a 5 horas. No se pierde nada, porque cada corrida vuelve a traer 3 días. Si algún día necesitás puntualidad exacta, Claude puede pasar la programación a Google Cloud Scheduler.
- **Los logins de Google vencen.** Con Workspace, Google suele pedir volver a iniciar sesión cada cierto tiempo. Eso afecta los comandos locales y a veces los conectores (que te piden reconectar), pero **no** la sincronización automática, que funciona sin claves.
- **Si la sincronización falla con "Garmin tokens expired"**, son 3 pasos: `login` → `export_tokens.sh` → volver a correr el workflow. El README que te genera Claude lo explica.
- **Sueño, HRV y peso** solo aparecen si tu dispositivo los registra: el reloj puesto de noche, o una balanza Garmin. Las tablas se llenan solas cuando empiezan a llegar esos datos.
- **Límites del MCP:** cada consulta devuelve como máximo 3.000 filas y dura como máximo 3 minutos. Para datos diarios personales sobra.
- **Costo esperado:** ~0 €. BigQuery, Secret Manager y GitHub Actions entran en sus capas gratuitas con este uso.

**Tiempo total estimado:** 1,5–3 h de tu atención, repartidas a lo largo del build, más la carga del historial, que corre sola.
