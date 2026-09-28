#!/usr/bin/env bash
# Run the listing tool against the ten camps in docs/ingest-test-set.md and push the results.
# Usage: ANTHROPIC_API_KEY=sk-ant-... scripts/run_ingest_eval.sh
set -uo pipefail
cd "$(dirname "$0")/.."
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY first}"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
mkdir -p eval
day=$(date +%F)
n=0
for url in \
  https://epl.providenceri.gov/recreation-department-camps/ \
  https://www.barrington.ri.gov/414/Camps \
  https://bristolri.gov/279/Summer-Camp \
  https://eastprovidenceri.gov/departments/recreation/summer-camp-0 \
  https://savebay.org/family-fun/camp/ \
  https://www.summeratsaintandrews.org/ \
  https://www.jewishallianceri.org/explore-programs/for-children/summer-j-camp \
  https://www.agawamhunt.org/camp \
  http://kidsjunctionri.com/summer-camp/ \
  "https://ymcagreaterprovidence-org.storage.googleapis.com/files/s3fs-public/2026-02/Kent%20Camp%20Info%202026.pdf"
do
  n=$((n+1))
  if python -m campfinder.ingest "$url" --json > "eval/$day-$n.json" 2> "eval/$day-$n.err"; then
    echo "$n ok"
  else
    echo "$n FAILED (see eval/$day-$n.err)"
  fi
done
git add eval
git commit -q -m "Ingest eval raw results, $day" && git push -q && echo "Pushed. Tell Claude it's done."
