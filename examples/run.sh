#!/bin/sh
# Rebuild the example report, then show that the invented edit is refused.
set -e
cd "$(dirname "$0")"
F=../skills/fitcheck/scripts/fitcheck.py
A="--resume resume.txt --posting posting.txt --reqs reqs.json --profile sample-profile.json"
python3 $F edits $A --edits edits.json > report.md
head -3 report.md
if python3 $F edits $A --edits bad-edits.json; then
  echo "bad edits were accepted" >&2
  exit 1
fi
