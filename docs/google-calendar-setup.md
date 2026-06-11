# Google Calendar API Setup for n8n Holiday Sync

The `Sync Holidays from Google Calendar` workflow needs OAuth2 credentials to read
the Thai public-holiday calendar (`en.th#holiday@group.v.calendar.google.com`).
This is a one-time setup.

---

## 1. Create a Google Cloud project

1. Go to <https://console.cloud.google.com/>.
2. Top bar → project dropdown → **New Project**.
   - Name: `hospitai-pom` (or anything)
   - Organization: leave default
3. Wait ~30s for it to be created, then switch the project dropdown to it.

## 2. Enable the Calendar API

1. Nav menu → **APIs & Services → Library**.
2. Search **Google Calendar API** → click → **Enable**.

## 3. Configure the OAuth consent screen

1. Nav menu → **APIs & Services → OAuth consent screen**.
2. User Type: **External** → Create.
3. Fill in:
   - App name: `HospitAI POM`
   - User support email: your email
   - Developer contact: your email
   - Leave logo / domain / scopes blank
4. **Scopes** step → Add or Remove Scopes → check
   `https://www.googleapis.com/auth/calendar.readonly` → Update → Save and Continue.
5. **Test users** step → Add your own Google account (`porsohani@gmail.com`).
   While the app is in *Testing* mode only listed test users can authorize it —
   that's fine for self-hosted use; you don't need to "Publish" it.
6. Save and finish.

## 4. Create OAuth client credentials

1. Nav menu → **APIs & Services → Credentials**.
2. **+ Create Credentials → OAuth client ID**.
3. Application type: **Web application**.
4. Name: `n8n local`.
5. **Authorized redirect URIs** — add exactly:
   ```
   http://localhost:5678/rest/oauth2-credential/callback
   ```
   (n8n's OAuth callback. If you change `WEBHOOK_URL` in `docker-compose.yml`,
   match that host:port here.)
6. Create.
7. Copy the **Client ID** and **Client secret** — you'll paste them into n8n next.

## 5. Add the credential in n8n

1. Open <http://localhost:5678>.
2. Left sidebar → **Credentials** → **+ Add Credential**.
3. Search **Google Calendar OAuth2 API** → Continue.
4. Paste **Client ID** and **Client Secret**.
5. Click **Sign in with Google** → choose your account → grant *See your calendars*.
   - If you see "Google hasn't verified this app", click **Advanced → Go to HospitAI POM (unsafe)** — expected while the app is in Testing mode.
6. n8n shows **Account connected** → **Save**.

## 6. Attach the credential to the workflow

1. Open workflow **Sync Holidays from Google Calendar**.
2. Click the **Fetch Thai Holidays** HTTP Request node.
3. **Credential for Google Calendar OAuth2 API** → pick the one you just created.
4. Save the workflow.

## 7. Test it

1. With the workflow open, click **Execute Workflow** (top right) — runs once
   without waiting for the 03:00 cron.
2. Inspect each node's output:
   - **Fetch Thai Holidays** → JSON with an `items[]` array of events.
   - **Map to Sync Payload** → `holidays: [{date, name, surcharge}, ...]`.
   - **POST /admin/holidays/sync** → `{deleted, inserted, window_start, window_end}`.
3. Verify in Postgres:
   ```bash
   docker compose exec db psql -U postgres -d oms -c "SELECT COUNT(*), MIN(date), MAX(date) FROM holidays;"
   ```

## 8. Activate the schedule

In the workflow header, flip the **Active** toggle on. It'll now run daily at
03:00 Asia/Bangkok (set via `GENERIC_TIMEZONE` in `docker-compose.yml`).

---

## Troubleshooting

- **`redirect_uri_mismatch`** — the URI in step 4.5 must match exactly,
  including `http` (not `https`) and the trailing path. Edit the OAuth client
  → re-add → save → retry sign-in.
- **`access_denied` / app not verified** — your Google account isn't in the
  Test Users list (step 3.5). Add it.
- **`invalid_grant` after a while** — refresh tokens expire after 7 days while
  the consent screen is in *Testing*. Either re-authorize, or move the consent
  screen to *In production* (no verification needed for sensitive scopes if you
  only use it yourself).
- **POST returns 404** — the n8n container must reach the backend at
  `http://backend:8000`. They share the compose network, so this works
  out-of-the-box; only an issue if you renamed the backend service.

## Cost

Google Calendar API is **free** for this usage (one read per day, well under
the 1M-requests/day quota). No billing account required.
