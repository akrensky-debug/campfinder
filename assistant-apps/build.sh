#!/usr/bin/env bash
# Package the ChatGPT plugin as a ZIP for the OpenAI Plugins dashboard.
#   assistant-apps/build.sh   ->   assistant-apps/dist/campfinder-chatgpt.zip
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
import json
p = json.load(open("chatgpt/plugin.json"))["extensions"]["com.openai"]
i, cases = p["interface"], p["review"]["test_cases"]
assert len(i["displayName"]) <= 30 and len(i["shortDescription"]) <= 30, "name/subtitle over 30 chars"
assert len(i["longDescription"]) <= 4000, "long description over 4000 chars"
assert all(len(x) <= 128 for x in i["defaultPrompt"]) and len(i["defaultPrompt"]) <= 3, "prompts"
assert len(cases["positive"]) == 5 and len(cases["negative"]) == 3, "need 5 positive and 3 negative cases"
url = json.load(open("chatgpt/mcp.json"))["mcpServers"]["campfinder"]["url"]
print("MCP server:", url)
PY
mkdir -p dist && rm -f dist/campfinder-chatgpt.zip
(cd chatgpt && zip -qr ../dist/campfinder-chatgpt.zip plugin.json mcp.json assets)
echo "Built dist/campfinder-chatgpt.zip"
