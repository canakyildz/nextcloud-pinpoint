# Security

## Reporting a vulnerability

Please email **contact@emincan.com** with "Pinpoint security" in the subject, and do not open a public
issue. You will get an answer within a few days. Fixes are released as a new version on the Nextcloud App
Store and noted in [CHANGELOG.md](CHANGELOG.md).

## How Pinpoint handles access and data

- **Every request is authenticated by AppAPI.** The ExApp only accepts requests that carry the app's
  secret (checked by `AppAPIAuthMiddleware`); requests that do not come through Nextcloud get a 401.
  The integration tests check this with missing headers, a wrong secret and a wrong app id.
- **Pinpoint acts as the user, never above them.** Files are read and Tables rows written with the
  requesting user's identity, so Nextcloud enforces that user's permissions. A user cannot run Pinpoint on
  a file or table they cannot open.
- **Jobs are private.** A review job is visible only to the user who created it; for anyone else it
  does not exist (404).
- **No copies of documents.** Files are read from Nextcloud when needed and kept only in memory. The
  ExApp's storage holds the review queue (extracted values with their quotes and positions), which is
  deleted after the retention period set by the admin (30 days by default) or when the user deletes it.
- **Document text goes to the configured text generation provider.** Pinpoint has no model of its own;
  it uses Nextcloud's TaskProcessing, so the admin decides where text is processed (a local provider such
  as llm2 keeps it on the server). The TaskProcessing task holding the prompt is deleted as soon as its
  result has been read.
