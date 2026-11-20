# How Pinpoint is built: a Python ExApp that uses and provides AI

These are notes on building Pinpoint as a Nextcloud External App (ExApp), for anyone writing their own.
Nextcloud's Python ExApp course (its example app is a pinboard) covers the basics.
This picks up where it stops: a Files action, a Vue 3 page, TaskProcessing from both sides, Tables, admin
settings, tests in CI, and the things that cost me time. Versions: Nextcloud 33–35, AppAPI as shipped with
them, nc_py_api 0.31.

## The shape of an ExApp

An ExApp is a web service in its own container. Nextcloud talks to it through AppAPI, and it talks back to
Nextcloud's APIs with a shared secret. Pinpoint is a FastAPI app built on
[nc_py_api](https://github.com/cloud-py-api/nc_py_api):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    set_handlers(app, enabled_handler, trigger_handler=PROVIDER_WORKER.trigger)
    ...
    yield

APP = FastAPI(lifespan=lifespan)
APP.add_middleware(AppAPIAuthMiddleware)   # 401 for anything that didn't come through AppAPI
APP.include_router(router)
```

`set_handlers` adds the three endpoints AppAPI calls (`/heartbeat`, `/init`, `/enabled`) and serves `js/` and
`img/`. Everything Pinpoint adds to Nextcloud is registered in `enabled_handler` and removed again when the app
is disabled, so disabling leaves nothing behind ([`main.py`](../ex_app/lib/main.py)):

```python
async def enabled_handler(enabled: bool, nc: AsyncNextcloudApp) -> str:
    if enabled:
        await nc.ui.top_menu.register("main", "Pinpoint", "img/app.svg")
        await nc.ui.resources.set_script("top_menu", "main", "js/pinpoint-main")
        await nc.ui.files_dropdown_menu.register_ex("extract_fields", "Extract fields", "/api/file-action",
                                                    mime="application/pdf, image/png, image/jpeg, ...")
        await nc.ui.settings.register_form(FORM)
        await nc.providers.task_processing.register(provider(APP_ID), task_type(APP_ID))
    else:
        ...  # the same, unregistered
    return ""  # a non-empty string is shown to the admin as an error
```

Use the async API (`AsyncNextcloudApp`, `anc_app`). The sync one is deprecated since nc_py_api 0.30, even
though the skeleton and several official apps still use it.

## Routes

Every path the browser may reach has to be declared in `info.xml`. Two things changed recently: routes are
matched against the path *with* its leading slash on Nextcloud 32.0.10+ and HaRP, and verbs are enforced since
33.0.11 / 34.0.6 / 35.0.3. Writing them the way the official apps now do works everywhere:

```xml
<route>
    <url>^\/?api\/.*</url>
    <verb>GET,POST,DELETE</verb>
    <access_level>USER</access_level>
</route>
```

The App Store's schema has no `<routes>` element, so a plain `xmllint --schema` of `info.xml` fails. The store
first runs its `pre-info.xslt`, which drops them, and AppAPI later reads them from the signed tarball. CI here
validates the same way the store does.

## Acting as the user

AppAPI lets an ExApp make requests as any user, so Pinpoint does every file and Tables call as the user who
asked. Nextcloud then applies that user's permissions and Pinpoint never needs its own checks for "can this
person read this file". The one thing Pinpoint owns is its review queue, where every query is scoped to the
user ([`store.py`](../ex_app/lib/pinpoint/store.py)), and another user's job is a 404, not a 403.

```python
nc = AsyncNextcloudApp()
await nc.set_user(user_id)
node = await nc.files.by_id(file_id)          # None if this user can't see it
data = await nc.files.download(node)
```

The same session reaches non-OCS endpoints too: `nc.ocs("GET", "/index.php/apps/tables/api/1/...",
response_type="json")`. That matters for Tables, where creating a row is still only on the v1 REST API.

## A Files action

`register_ex` adds an entry to the Files context menu. The `mime` argument is a comma-separated list matched by
substring. When the handler answers `{"redirect_handler": "main/new"}`, AppAPI opens the ExApp's page and
appends `?fileIds=…`, which is how "Extract fields" lands on Pinpoint's page with the files already chosen.

## A Vue 3 page

The page lives under `/apps/app_api/embedded/<appid>/<menu entry>/`, and AppAPI injects the registered script
with `Util::addScript`. That means **a classic script, not a module**, so the bundle has to be one
self-contained file. Pinpoint builds it with Vite as an IIFE ([`vite.config.ts`](../vite.config.ts)):

```ts
rollupOptions: {
    input: 'src/main.ts',
    output: { format: 'iife', inlineDynamicImports: true, entryFileNames: 'pinpoint-main.js' },
},
```

With that, Vue 3, `@nextcloud/vue` 9 and `@nextcloud/dialogs` 8 (the Files picker) all work inside the
embedded page. The official examples are still Vue 2 with webpack.

Two things to get right in the frontend:
- Call your API through `/apps/app_api/proxy/<appid>/…`. AppAPI authenticates the user and forwards it.
- Read the router's base from `window.location`. The page is reachable with and without `/index.php`
  depending on URL rewriting, and a hard-coded base breaks deep links.

## Using TaskProcessing as a client

Pinpoint has no model. It schedules a `core:text2text` task as the user and waits for it, so the admin's
choice of provider applies (llm2, LocalAI, OpenAI…), quotas included
([`nextcloud.py`](../ex_app/lib/pinpoint/nextcloud.py)):

```python
task = await nc.ocs("POST", "/ocs/v2.php/taskprocessing/schedule", json={
    "input": {"input": prompt}, "type": "core:text2text", "appId": "pinpoint", "customId": f"pinpoint:{job_id}",
})
# poll /ocs/v2.php/taskprocessing/task/{id} until STATUS_SUCCESSFUL, then delete the task
```

The prompt contains document text, so Pinpoint deletes the task once it has the answer.

The model's answer is never trusted as given. Small local models write things like `"value": 7829,00`
(invalid JSON, the number copied in French notation), so the parser repairs a few known patterns and otherwise
asks the model once to fix its own answer.

## Being a TaskProcessing provider

Pinpoint also offers its own task type, so the Assistant can extract fields without Pinpoint's UI. A custom
task type is described by its input and output shapes, and the Assistant renders the form from them with no
frontend code ([`provider.py`](../ex_app/lib/pinpoint/provider.py)). The slot `name` is both the key and the
label the user sees, so name slots for people: `"Document"`, `"Document type"`, `"Evidence"`.

Work arrives by polling `next_task`. Since Nextcloud 33 AppAPI also calls the ExApp's `/trigger` endpoint when
a task is scheduled, so Pinpoint waits on an event and keeps a slow poll as a fallback. A file given to a task
may not be in the user's storage (the Assistant uploads to app data), so it's read through the provider
endpoint `/ocs/v2.php/taskprocessing/tasks_provider/{task}/file/{file}`.

## Admin settings with no settings page

Declarative settings are a schema Nextcloud renders. Pinpoint's appear under *Administration → Artificial
intelligence* and are read back with `nc.appconfig_ex.get_values(...)`, cached for a minute
([`settings.py`](../ex_app/lib/pinpoint/settings.py)).

## Testing an ExApp

Three layers, all in CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)):

1. **Unit and API tests** against an in-memory stand-in for Nextcloud. Everything Pinpoint needs from Nextcloud
   goes through one small `Gateway` interface, which makes this easy.
2. **Integration tests** against the official Nextcloud image (33, 34 and 35), with Pinpoint registered
   through AppAPI exactly as in development. The model is a tiny OpenAI-compatible server returning the ground
   truth, behind the real `integration_openai` app, so the whole TaskProcessing path is exercised
   deterministically. The tests also check that the ExApp answers 401 to requests without AppAPI's headers,
   with a wrong secret or a wrong app id.
3. **The release image under HaRP** ([`dev/harp.sh`](../dev/harp.sh)): AppAPI deploys the container and reaches
   it through HaRP's tunnel, the way an admin's server will.

## Things that cost me time

- **AppAPI injects scripts as classic scripts.** An ES module bundle loads and silently does nothing.
- **HaRP reaches the ExApp through Nextcloud's own URL under `/exapps/`.** The web server in front of Nextcloud
  must proxy `/exapps/` to HaRP. Without it, registration waits for a heartbeat that comes back 404 from
  Nextcloud ("ExApp … is disabled").
- **A Docker image that isn't published yet** can still be deployed: map the registry to `local` on the
  daemon (`occ app_api:daemon:registry:add <daemon> --registry-from=ghcr.io --registry-to=local`) and AppAPI
  uses the local image instead of pulling.
- **Tables wants `baseNodeType` spelled out.** Its permission middleware reads the request, not the method's
  default, so `POST /api/2/columns/text` without `"baseNodeType": "table"` fails with "Invalid node type".
- **The TaskProcessing worker caches app config for its whole run.** After pointing a provider somewhere
  else, restart `occ background-job:worker` or it keeps calling the old URL for up to a minute.
- **Long polls and keep-alive.** Apache closes idle connections after 5 seconds. Polling with longer gaps on
  the same connection sometimes fails with "remote end closed connection". Idempotent GETs are retried.
- **Tests with session cookies.** A test client that logs in with basic auth gets a session cookie back, and a
  later WebDAV call with that cookie needs a CSRF token. Sending `OCS-APIRequest: true` marks the calls as API
  calls.
- **`overwrite.cli.url`** is what AppAPI's `info/nextcloud_url/absolute` returns. Links Pinpoint writes into
  Tables and notifications come from it, so set it to the address users actually use.
