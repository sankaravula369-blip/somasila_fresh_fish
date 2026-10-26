# SFF: local startup and deployment

The project uses SQLite for local development and supports PostgreSQL in
production. Set `DATABASE_URL` to select PostgreSQL; otherwise
`DATABASE_PATH` selects the local SQLite file, defaulting to
`python/data/sff.db`. Keep both local database files outside source control.

## Run locally on Windows

From the project root in the VS Code terminal:

```powershell
.\start_server.bat
```

The script checks port 5000, Python, Flask, and the owner WhatsApp number. If
the number is not set in the environment, it prompts for the existing owner
number in international digits-only format (country code followed by number;
no `+`, spaces, or dashes). The value is only set for that server process.

To install dependencies first, run:

```powershell
cd ".\python"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
.\start_server.bat
```

The launcher uses that `.venv` automatically when present. If Flask is
missing, it prints the install command. Stop with **Ctrl+C** in the server
terminal; restart by stopping the process and running `.\start_server.bat`
again. Do not run a second copy on the same port.

To enable the owner dashboard in that terminal session, set its password
before launching:

```powershell
$env:SECRET_KEY = py -3 -c "import secrets; print(secrets.token_hex(32))"
$env:OWNER_PASSWORD = Read-Host "Set the owner dashboard password"
```

The launcher prompts for `OWNER_WHATSAPP_NUMBER` if it is not already set.
These environment values are not saved permanently when that terminal closes.

Local URLs:

- Storefront: `http://127.0.0.1:5000/`
- Fish products page: `http://127.0.0.1:5000/products`
- Health check: `http://127.0.0.1:5000/healthz`

The Flask development server is for local testing only. It is not a
24/7/public hosting service.

## Environment variables

- `SECRET_KEY`: a randomly generated Flask secret. Keep it private.
- `DATABASE_URL`: PostgreSQL connection URL supplied by Render. When set, the
  app uses PostgreSQL; do not commit or print this credential.
- `DATABASE_PATH`: SQLite file path. For local use, leave unset to use
  `python/data/sff.db`.
- `OWNER_WHATSAPP_NUMBER`: existing owner number with country code, digits
  only. Do not add a plus sign or separators.
- `OWNER_PASSWORD`: password for the owner orders page.
- `PUBLIC_SITE_URL`: optional preferred public canonical origin, for example
  `https://YOUR-ACTUAL-DOMAIN` (no path or trailing slash). Set this in
  production after the real Render hostname or custom domain is known.
- `PORT`: listener port; defaults to `5000`.
- `SFF_HOST`: local Flask listener; defaults to `0.0.0.0`.
- `APP_ENV=production`: enables secure session-cookie settings.

Order messages are created by the server only after the configured database
transaction commits. The browser then shows the WhatsApp button; the customer
still has to press **Send** in WhatsApp.

## Public hosting with Render

The existing frontend is Flask-rendered HTML with static CSS and JavaScript;
it is not a separate Vercel frontend. Deploying the templates, static assets,
and API together as one Render web service keeps API requests same-origin,
avoids CORS configuration, and preserves existing relative API URLs.

`render.yaml` configures a paid Render Python web service using Gunicorn (not
Flask's development server), a health check, environment variables, and a
managed Render PostgreSQL database. The database and web service plans
(`0.5c-1g` and `0.5c-512mb`) are paid; check current prices and
data-retention terms in Render before creating resources. A paid service
avoids the automatic spin-down
associated with free web instances, but no hosting provider can guarantee
uninterrupted availability during maintenance or outages.

### Before deployment

1. Install Git for Windows if `git --version` is not recognized in the VS Code
   terminal. Create a **private** repository on GitHub.
2. From the project root, initialize Git if this folder is not already a
   repository, then confirm the repository status:

   ```powershell
   git init -b main
   git status --short
   ```

   Skip `git init -b main` if this folder is already a Git repository.
   Confirm the database and secret files are ignored:

   ```powershell
   git check-ignore python\data\sff.db
   git check-ignore sff.db
   ```

   Both database checks should report that the paths are ignored. Do not
   force-add database files, `.env` files, passwords, or secret keys.
3. Stage and inspect only the application/deployment files:

   ```powershell
   git add .gitignore DEPLOYMENT.md render.yaml start_server.bat python
   git status --short
   ```

   Verify the staged list contains no SQLite database or environment file.
   Then commit and push, replacing the remote URL with your private GitHub
   repository:

   ```powershell
   git commit -m "Prepare SFF for Render deployment"
   git remote add origin https://github.com/YOUR-GITHUB-NAME/YOUR-PRIVATE-REPOSITORY.git
   git push -u origin main
   ```

### Create the Render service

1. Sign in to Render and select **New + > Blueprint** (sometimes shown as
   **New > Blueprint**).
2. Connect GitHub and authorize access to the private SFF repository. Select
   the repository and `main` branch, then continue.
3. Render reads the root `render.yaml`. Check the preview before applying:
   - Runtime: Python, root directory: `python`.
   - Web service plan: `0.5c-512mb` (paid).
   - Build: `pip install -r requirements.txt`.
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60`.
   - Health check: `/healthz`.
   - Managed PostgreSQL: `sff-postgres`, compute plan `0.5c-1g` with 1 GB
     initial storage, in the same Oregon region as the
     service. `DATABASE_URL` is linked from the database's private
     `connectionString`; no database password belongs in Git.
   The storefront and API are served from the same Flask origin, so existing
   relative `/api/...` requests need no separate production URL or CORS setup.
4. Review the web-service and PostgreSQL prices displayed by Render. This
   Blueprint uses paid plans; do not continue unless the current costs are
   acceptable to you.
5. Apply/create the Blueprint. When Render requests values for the
   `sync: false` variables, enter:
   - `OWNER_WHATSAPP_NUMBER`: the existing owner number, international digits
     only (country code included; no plus sign or spaces).
   - `OWNER_PASSWORD`: a strong password for the owner dashboard.

   Keep these private. Render generates `SECRET_KEY`; do not replace it with a
   value committed to Git. `DATABASE_URL` and `APP_ENV` are already set by
   `render.yaml`. Render supplies `PORT` to the process automatically.
6. Wait for the first deploy to finish. In Render, confirm the service is
   **Live** and its `/healthz` check passes. If it fails, open the service's
   **Logs** and fix the reported build/start/configuration error before
   continuing.
7. Open the service's **Settings** page and copy the exact HTTPS URL Render
   assigned. No URL should be guessed or copied from a local VS Code address.
8. Visit the assigned HTTPS URL with `/`, `/products`, `/api/products`,
   `/healthz`, `/robots.txt`, and `/sitemap.xml`. Confirm the first four are
   healthy (the products API returns catalog JSON) and the sitemap contains
   only the actual production homepage and `/products`.
9. Place a small test order. Confirm it appears in **My Orders** and that the
   generated WhatsApp link opens a chat with the owner number. The current
   feature saves the order first and then asks the customer to open WhatsApp
   and press **Send**; it does not automatically send a WhatsApp message.
   Restart or redeploy once, then verify the order remains in PostgreSQL.
10. Open the HTTPS URL on a phone using mobile data (not the laptop's
    `localhost`) and check the storefront and ordering flow.

After the first deployment, check the web service's **Settings** and ensure
automatic deploys are enabled for the connected branch. Render will then
deploy future pushes to that branch; review **Events** and **Logs** after
each deployment.

Render PostgreSQL stores **new hosted products and orders** persistently. It
does not automatically copy the local `python\data\sff.db` (or the separate
root-level `sff.db`) into the hosted database. The local databases remain on
your computer and are excluded from Git. If you need historical orders or
custom catalog changes online, keep a backup and plan a separate, verified
migration; do not upload a database file to a public repository. The app
creates its tables and inserts the default catalog only if the hosted product
table is empty. It does not reset or delete existing PostgreSQL rows.

The Render service does not automatically spin down on the configured paid
`0.5c-512mb` plan. Render's Free web services spin down after 15 minutes without
traffic and can take about a minute to wake; Free Postgres expires after 30
days and has no backups. Those free plans are not suitable for persistent
production orders. Check Render's current plan terms before deployment. Paid
plans improve availability and persistence but do not promise zero downtime.

The customer WhatsApp action remains a user-confirmed click-to-chat link.
Automatic WhatsApp messages require separate WhatsApp Business Platform/API
setup, approved credentials, and a webhook or server-side notification
integration; do not place those credentials in frontend code.

### Canonical domain and HTTPS

Render provides HTTPS for the assigned service hostname. To use a custom
domain, add it under the service's **Settings > Custom Domains**, then copy
the DNS records Render displays into your domain registrar's DNS settings.
Wait until Render reports the custom domain as verified and HTTPS is active.
In the service's **Environment** settings, optionally set `PUBLIC_SITE_URL` to
the preferred exact origin, such as `https://www.your-real-domain.example`
(replace with the domain you own; no trailing slash, path, or localhost), and
deploy the change. If unset, production SEO URLs use the incoming HTTPS host.

Render's SQLite disk preserves data across deploys, but the service is a
single-instance design and the disk has a separate cost. For larger or
multi-instance production use, configure managed PostgreSQL and migrate the
existing SQLite data before switching `DATABASE_PATH` to another database
format; this code currently supports SQLite paths only.

## SEO, custom domain, and Google Search Console

The public storefront and `/products` page include page titles, descriptions,
canonical links, Open Graph tags, structured data, and server-rendered product
cards. The app serves `/robots.txt` and `/sitemap.xml`; the sitemap lists only
the public storefront routes. Owner orders, order APIs, and health checks
return `X-Robots-Tag: noindex` and are not listed in the sitemap. Robots are
allowed to read those response headers; `robots.txt` alone is not a reliable
way to prevent indexing.

The homepage title is `Somasila Fresh Fish | Fresh Fish and Dry Fish Supply`.
On localhost, the app omits canonical/absolute social URLs and `/robots.txt`
does not advertise a sitemap. `/sitemap.xml` returns HTTP 503 until a public
origin is available; this avoids publishing localhost URLs. In production,
the actual HTTPS request host is used unless `PUBLIC_SITE_URL` specifies the
preferred public canonical origin.

After the first successful deployment:

1. Open the real public HTTPS URL and check `/`, `/products`, `/robots.txt`,
   and `/sitemap.xml`. The sitemap uses the incoming production host by
   default, or the configured `PUBLIC_SITE_URL` if provided. Do not submit a
   local development sitemap.
2. Open Google Search Console at <https://search.google.com/search-console>.
   Choose **Add property**. A **Domain** property covers all subdomains and
   HTTP/HTTPS variants; verify it by adding Google's TXT record to your
   domain's DNS provider, then click **Verify**. If you only have the Render
   hostname, use a **URL prefix** property and the HTML-tag verification
   method; put the token from Google in the Render environment variable
   `GOOGLE_SITE_VERIFICATION`, save, redeploy, then click **Verify**.
5. In Search Console, open **Sitemaps**, submit
   `https://YOUR-ACTUAL-DOMAIN/sitemap.xml`, and check for a successful read.
   Use **URL inspection** for the homepage and `/products`, then choose
   **Request indexing** if offered.
6. Check the Search Console indexing report over the following days and weeks.
   Google controls crawling and indexing; submission does not guarantee
   appearance, ranking, or a particular time to index.

No production domain is configured in this project yet and it has not been
deployed or indexed. Replace the example URL above with the actual domain
assigned by Render or connected by you.
