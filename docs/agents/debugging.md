# Debugging — real failure modes

One playbook per symptom that has actually occurred. Prod logs generally: the
`production-logs` skill, or
`az containerapp logs show -n ca-loan-army-backend -g rg-loan-army-westus2 --tail 100`.

## Playbook: "Deploy Frontend" fails with 403 on an MCR image

Symptom: the static-web-apps-deploy step dies pulling
`mcr.microsoft.com/appsvc/staticappsclient:stable` → 403 Forbidden.
Transient Microsoft registry flake, NOT a code/bundle bug.

```bash
gh run rerun <run_id> --failed
```

## Playbook: "data isn't showing" on a page, but the API has it

Oversized/slow responses block rendering even when the data is correct.

```bash
curl -s <url> | head -c 2000          # 1. is the field even there?
time curl -s <url> -o /tmp/x.json     # 2. >5s = serious
wc -c /tmp/x.json                     # 3. >1MB for a LIST endpoint = suspicious;
                                      #    >5MB = base64 images / duplicated blobs
```

Fix pattern: list endpoints return metadata + excerpts only, never full content.

## Playbook: need admin/diagnostic access to prod from a local shell

`az containerapp exec` needs a TTY; the direct DB host is IPv6-only. Use the
prod HTTP admin endpoints — auth is two-factor: `Authorization: Bearer <token>`
AND `X-API-Key: <admin key>`. Mint the Bearer locally with itsdangerous
`URLSafeTimedSerializer(secret_key=<prod inline secret-key>, salt='user-auth')
.dumps({'email': <admin email>, 'role': 'admin', 'iat': <now>})`.
Read CURRENT inline secrets (Key Vault copies are stale):

```bash
az containerapp secret show -g rg-loan-army-westus2 -n ca-loan-army-backend \
  --secret-name secret-key --query value -o tsv   # never echo into transcripts
```

Raw SQL: session pooler host + `PGOPTIONS='-c default_transaction_read_only=on'`
for read-only work. Never print secret values into conversation output.

## Playbook: prod /api/health flapping (000) during a bulk operation

Cause is capacity, not code: 0.5 CPU / 1Gi / max 2 replicas; each force_full
sync holds a worker ~7s and starves the probe.

```bash
az containerapp update -g rg-loan-army-westus2 -n ca-loan-army-backend \
  --cpu 1.0 --memory 2Gi --min-replicas 2 --max-replicas 4   # scale UP first
# run the bulk op in health-gated batches (abort on first 000), then scale back
```

Proven pattern: scale up → concurrency ~4 in batches of ~20 → scale down.

## Playbook: POST 405s on theacademywatch.com but works elsewhere

The SWA front door can 405 a POST at the custom domain. Test POSTs against the
container-app FQDN directly (`https://ca-loan-army-backend.<env>.azurecontainerapps.io`),
not `theacademywatch.com/api/*`, before debugging the backend.

## Playbook: prod DB disk growth

`api_cache` dominates. A pg_cron job `purge-expired-api-cache` (daily 03:30 UTC)
is live — record at `migrations/maintenance/api_cache_purge_cron.sql`. Inspect:
`select * from cron.job;` / `cron.job_run_details`. DELETE doesn't shrink disk
(VACUUM FULL is one-time and manual — never schedule it). `newsletters` rows are
~5MB each (base64-embedded images) — known TODO to externalize to Blob storage.
Note: the default connected Supabase account may be a different org — prod is
project ref `snqwamzutbcbjgusubsa`.

## Playbook: exercising Film Room locally (no cloud GPU)

Runs against the LOCAL DB (`soccer_newsletter`), never prod. Load real spike
artifacts: `src/scripts/load_video_artifacts.py --match-id N --artifacts-dir
spike/video-analysis/results/...`. Media routes need a match-scoped media token
(`auth.py` `mint_media_token`, salt `video-media`). Known prod gaps: crop
serving 501s (worker doesn't persist crops to blob); SWA CSP lacks
`media-src blob:`.
