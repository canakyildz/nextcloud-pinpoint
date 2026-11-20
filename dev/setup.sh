#!/usr/bin/env sh
# Prepare the development (and CI) Nextcloud: apps, AI provider, background jobs, and Pinpoint registered
# with AppAPI as a manual-install ExApp running in the "pinpoint" compose service.
#
#   LLM_URL    OpenAI-compatible endpoint for text generation (default: Ollama on the host)
#   LLM_MODEL  model name (default: qwen2.5:7b)
set -eu
cd "$(dirname "$0")/.."
OCC=dev/occ
LLM_URL=${LLM_URL:-http://host.docker.internal:11434/v1}
LLM_MODEL=${LLM_MODEL:-qwen2.5:7b}

install() { $OCC app:install "$1" >/dev/null 2>&1 || $OCC app:enable "$1"; }

echo "Apps"
$OCC app:enable app_api
install tables
install integration_openai
[ "${WITH_ASSISTANT:-1}" = 1 ] && install assistant
for app in firstrunwizard nextcloud_announcements recommendations; do $OCC app:disable "$app" >/dev/null 2>&1 || true; done

echo "System"
$OCC config:system:set overwrite.cli.url --value=http://localhost:8080
$OCC background:cron

echo "Text generation via $LLM_URL ($LLM_MODEL)"
$OCC config:app:set integration_openai url --value="$LLM_URL"
$OCC config:app:set integration_openai default_completion_model_id --value="$LLM_MODEL" --lazy
$OCC config:app:set integration_openai service_name --value="Development model" --lazy
$OCC config:app:set integration_openai max_tokens --value=4000 --lazy
$OCC config:app:set integration_openai request_timeout --value=600 --lazy
for provider in t2i_provider_enabled stt_provider_enabled tts_provider_enabled; do
  $OCC config:app:set integration_openai "$provider" --value=0
done

echo "AppAPI"
$OCC app_api:daemon:register manual_install "Manual Install" manual-install http pinpoint http://nextcloud 2>/dev/null \
  || echo "daemon already registered"
$OCC app_api:app:unregister pinpoint --silent --force 2>/dev/null || true
$OCC app_api:app:register pinpoint manual_install --json-info "$(python3 dev/register_info.py)" --wait-finish
$OCC app_api:app:list

# The task worker caches app config for its whole run; restart it so it uses the provider set above.
docker compose -f dev/docker-compose.yml restart taskworker >/dev/null 2>&1 || true
