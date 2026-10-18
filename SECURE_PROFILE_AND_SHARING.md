# HEALTHSYNC-AI: persisted Health Profile and Secure Sharing

## What changed

- Health profile fields are stored in PostgreSQL per authenticated user through `GET/PUT /api/secure-sharing/profile`; they are no longer stored in browser localStorage.
- Secure sharing creates an actual database grant for selected record IDs, sends a time-limited link to the named recipient through SMTP, supports listing and revoking shares, and audits share creation, access, file access and revocation.
- Share tokens are random high-entropy values. Only SHA-256 token hashes are stored in the database. Public endpoints return only records scoped to the share; original-file requests check both the share's record IDs and owner storage directory.
- The public `/shared/<token>` route displays the selected records and links to their original documents. Expiry defaults to 72 hours and can be 24 hours or 7 days. The patient can revoke an active share.

## Required configuration

Set these in the root `.env` beside `docker-compose.yml`:

```dotenv
PUBLIC_APP_URL=https://your-real-healthsync-domain.example
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-sender@gmail.com
SMTP_APP_PASSWORD=your-gmail-app-password
SMTP_FROM=your-sender@gmail.com
JWT_SECRET=replace-with-a-long-random-secret
```

`PUBLIC_APP_URL` must be the externally reachable HTTPS frontend URL. Sharing is intentionally disabled when it is missing or not HTTPS. SMTP must be configured: the API does not create a grant if email delivery fails.

Then rebuild:

```bash
docker compose up --build -d
```

The app creates new database tables on startup via SQLAlchemy `create_all`. For an existing production database, use formal versioned migrations (Alembic) rather than relying on `create_all` for future schema changes.

## Endpoints

- `GET /api/secure-sharing/profile`
- `PUT /api/secure-sharing/profile` body `{ "data": { ...allowed profile fields... } }`
- `POST /api/secure-sharing/shares` with recipient name/email, selected `record_ids`, purpose and expiry hours
- `GET /api/secure-sharing/shares`
- `POST /api/secure-sharing/shares/{id}/revoke`
- Public read-only recipient page: `/shared/{token}`
- Public scoped record file: `/api/secure-sharing/shared/{token}/records/{record_id}/file`

## Security notes before real clinical deployment

This is a real backend-backed time-limited bearer-link implementation, but it is not a claim of regulatory certification or complete production hardening. Anyone possessing the unexpired emailed link can access the selected records until expiry/revocation. For a clinical production release, add recipient identity verification (e.g. one-time code to recipient email), rate limiting, CSP/referrer policy, TLS termination and secure reverse-proxy configuration, malware scanning, formal database migrations, key management, backups/retention policies, and a legal/privacy review for the deployment jurisdiction. Avoid sharing through HTTP. The patient should share the minimum records needed.

The profile currently stores data in the protected application database under account authorization; database/storage encryption-at-rest and key management depend on your deployment infrastructure and must be configured for production.


### Local development URL

For local development, set `PUBLIC_APP_URL=http://localhost:5173` in the project-root `.env` file and keep `ENVIRONMENT=development`. HTTP is allowed only for `localhost` and `127.0.0.1` in development; non-local deployments still require HTTPS. A localhost share link works only on the same computer running the frontend. To let someone on another device access the link, use a trusted HTTPS tunnel or deploy the frontend over HTTPS.
