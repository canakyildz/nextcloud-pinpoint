#!/bin/bash
# SPDX-FileCopyrightText: 2025 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# From nextcloud/app-skeleton-python: healthy while the HaRP tunnel client runs.

if [ -f /frpc.toml ] && [ -n "$HP_SHARED_KEY" ]; then
  if pgrep -x "frpc" > /dev/null; then
      exit 0
  else
      exit 1
  fi
fi
