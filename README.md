# fitcheck

A Claude agent skill that compares a resume with a job posting: match score, missing skills, ATS format checks, evidence-backed edits, and a cover letter on request.

Claude reads the posting. A standard-library Python script does the counting, so the same inputs always give the same score.

- Every requirement needs a verbatim quote from the posting, or the script rejects it.
- Edits are rejected when they add a posting skill or a number that your resume and profile do not back up. This check covers listed skills, numbers and phrases, so still read every edit.
- Your profile lives in `~/.fitcheck/profile.json`, outside the repo.

## Score

| Part | Weight |
|---|---|
| Required skills | 50 |
| Preferred skills | 15 |
| Job title | 10 |
| Years and degree | 10 |
| Format | 15 |

Parts the posting does not mention are dropped and the rest rescaled to 100. This is fitcheck's own formula. It is not a real ATS score and does not predict interviews. Requirements are extracted by Claude, so two separate extractions of one posting can differ.

Also reported, without changing the score: how often each skill appears in the resume and the posting, soft skills, searchability (title, contact, sections, dates, file name), recruiter tips (measurable results, word count, cliches, job level, web presence), and formatting (pages, page size, fonts, images).

## Install

Needs Python 3.9+ and `pdftotext` (poppler) for PDFs. DOCX, TXT and MD need nothing else.

```bash
claude plugin marketplace add https://github.com/taneracar/resume-fitcheck.git
```

```bash
claude plugin install fitcheck@fitcheck
```

Then, in Claude Code, run `/fitcheck:fitcheck` or ask it to check a resume against a posting.

Scanning runs on your machine, but Claude reads your resume and the posting, so both go to the model you use in Claude Code. The skill can also read `~/.fitcheck/profile.json`.

## Example

Everything in `examples/` is fictional. `sh examples/run.sh` rebuilds [the report](examples/report.md) (75, or 85 with one backed edit) and then tries an invented edit:

```
fitcheck: edits rejected:
  edit 1: adds "Kubernetes", which the profile says never to claim
  edit 1: adds "Kubernetes" with no evidence in the resume or profile
  edit 1: number 60 is not in the resume or profile
```

## Limits

- Matching is on words, so a word used in another sense can match. The report shows the surrounding resume text so it can be caught.
- English postings and resumes only for section names, degrees and dates.
- Scanned (image-only) resumes are flagged, not read.

## Test

```bash
python3 -m unittest discover -s tests
```

## License

MIT. Not affiliated with any ATS or resume-scanning company.
