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
ln -s "$PWD/skill" ~/.claude/skills/fitcheck
```

Then, in Claude Code: `/fitcheck` with a resume and a posting.

## Test

```bash
python3 -m unittest discover -s tests
```
