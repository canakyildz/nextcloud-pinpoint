# Development

## What you need

Docker, Python 3.12 (`uv` makes it quick), Node 22, and for real extractions a text model. The easiest is
[Ollama](https://ollama.com) on the host with `ollama pull qwen2.5:7b`. Start it with a bigger context window
than the default: `OLLAMA_CONTEXT_LENGTH=16384 ollama serve`.

## Local stack

```bash
make venv frontend
make dev-up
```

`make dev-up` starts `dev/docker-compose.yml` and runs `dev/setup.sh`:

| Service | What it is |
|---|---|
| `nextcloud` | the official `nextcloud:35-apache` image (override with `NEXTCLOUD_TAG=33-apache`) on http://localhost:8080, user `admin` / `admin` |
| `cron`, `taskworker` | background jobs, and a worker that runs AI tasks as soon as they're scheduled, as the admin manual recommends |
| `pinpoint` | the ExApp, built from the `dev` target with `ex_app/` mounted, so a container restart picks up Python changes |

`setup.sh` installs Tables, the Assistant and the OpenAI/LocalAI integration, points the integration at
`LLM_URL` (Ollama on the host by default), and registers Pinpoint with AppAPI as a **manual-install** ExApp
whose address is the `pinpoint` service. Rerun it any time, it's idempotent.

After changing Python code: `docker compose -f dev/docker-compose.yml restart pinpoint`.
After changing the frontend: `npm run build` (or `npm run dev` to rebuild on save) and reload the page.

## Testing the real deployment path (HaRP)

Manual-install skips the part AppAPI does in production: pull the image, start the container, connect it
through HaRP. `dev/harp.sh` does that with the release image built locally:

```bash
dev/harp.sh
pytest -m integration tests/integration -k "not exapp_refuses and not heartbeat"
```

The two deselected tests call the ExApp's port directly, which HaRP deliberately doesn't expose (it reaches the
app over a unix socket through its FRP tunnel). To go back to manual-install, run `dev/setup.sh` again.

## Tests and evals

```bash
make lint             # ruff, mypy --strict, vue-tsc
make test             # unit and API tests (in-memory Nextcloud); OCR tests need tesseract
make test-integration # real Nextcloud + deterministic mock model (what CI runs on 33, 34 and 35)
make eval             # the verification layer against injected faults, with CI thresholds
make eval-model LLM_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b
```

Tesseract isn't needed on the host; the scanned-document tests and evals are skipped without it. To run them,
use the dev image: `docker run --rm -v "$PWD":/repo -w /repo pinpoint-dev:latest python3 evals/run.py oracle`.

The dataset is generated: `python evals/generate.py` rewrites `evals/dataset/` from a fixed seed and refuses
to write a document whose ground-truth quotes aren't in its own PDF.

## Screenshots

`make screenshots` drives your installed Google Chrome with playwright-core against the local stack and
rewrites `screenshots/` and the review GIF (ffmpeg needed for the GIF). It expects a few extractions to exist
(by default `invoice-07.pdf` for the review screen and `invoice-04.pdf` for the saved Tables row).

## Where things are

| Path | |
|---|---|
| `ex_app/lib/main.py` | lifespan, `enabled_handler` (everything Pinpoint registers in Nextcloud), FastAPI app |
| `ex_app/lib/pinpoint/document.py` | PDF text layer and OCR words with positions, page rendering |
| `ex_app/lib/pinpoint/anchor.py` | finding a quote in the document's words |
| `ex_app/lib/pinpoint/values.py` | numbers and dates as documents write them |
| `ex_app/lib/pinpoint/verify.py` | field statuses and cross-checks |
| `ex_app/lib/pinpoint/prompt.py`, `pipeline.py` | the prompt, parsing the answer, the whole extraction |
| `ex_app/lib/pinpoint/nextcloud.py` | every call to Nextcloud: files, Tables, TaskProcessing, notifications |
| `ex_app/lib/pinpoint/service.py`, `store.py`, `api.py` | jobs, the SQLite review queue, HTTP routes |
| `ex_app/lib/pinpoint/provider.py` | the Assistant task type and its worker |
| `ex_app/lib/pinpoint/settings.py` | declarative admin settings |
| `src/` | Vue 3 frontend |
