#!/bin/sh
set -eu

# Loopback, Docker host aliases, RFC1918 private LAN ranges, link-local,
# and carrier-grade NAT ranges should bypass HTTP proxies for local services.
DEFAULT_NO_PROXY="localhost,127.0.0.1,::1,host.docker.internal,docker.internal"
DEFAULT_NO_PROXY="${DEFAULT_NO_PROXY},10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
DEFAULT_NO_PROXY="${DEFAULT_NO_PROXY},169.254.0.0/16,100.64.0.0/10"

merge_no_proxy() {
  CURRENT_NO_PROXY="$1" DEFAULT_NO_PROXY_VALUE="$2" python - <<'PY'
import os

values = []
seen = set()
for raw in (os.environ.get("CURRENT_NO_PROXY", ""), os.environ.get("DEFAULT_NO_PROXY_VALUE", "")):
    for item in raw.split(","):
        item = item.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        values.append(item)

print(",".join(values))
PY
}

MERGED_NO_PROXY="$(merge_no_proxy "${NO_PROXY:-${no_proxy:-}}" "$DEFAULT_NO_PROXY")"
export NO_PROXY="$MERGED_NO_PROXY"
export no_proxy="$MERGED_NO_PROXY"
exec "$@"
