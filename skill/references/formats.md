# File formats

## reqs.json

```json
{
  "company": "Initech",
  "role": "Full-Stack Engineer",
  "skills": [
    {"name": "React", "match": ["React.js"], "priority": "required", "quote": "Strong React and TypeScript"},
    {"name": "Python", "match": ["Java", "Go"], "priority": "required", "quote": "Experience with Java, Go or Python"}
  ],
  "years": {"min": 4, "quote": "4+ years of experience"},
  "degree": {"level": "bachelor", "quote": "Bachelor's degree required"},
  "blockers": [{"reason": "U.S. citizenship required", "quote": "Must be a U.S. citizen"}]
}
```

`name` or a `match` term must appear in the quote. Omit `years` or `degree` when the posting does not ask, and omit `degree` when equivalent experience is accepted. Levels: associate, bachelor, master, doctorate.

## ~/.fitcheck/profile.json

```json
{
  "resume": "~/cv/resume.pdf",
  "years_experience": 2,
  "skills": [{"name": "PostgreSQL", "aliases": ["Postgres"], "evidence": "Where it was used, for what, with which result"}],
  "facts": ["Other true statements and numbers that edits may use"],
  "never_claim": [{"name": "Kubernetes", "aliases": ["k8s"], "note": "User said no, 2026-11-24"}],
  "blockers": ["U.S. citizenship or clearance required"],
  "style": "Plain sentences.",
  "banned_phrases": ["leverage"],
  "apply": "How to turn replace.json into a finished resume"
}
```

All fields are optional. `never_claim` wins over `skills`, so remove the entry if the user's answer changes.

## edits.json

```json
{"edits": [{"old": "exact text, appearing once in the resume", "new": "replacement", "why": "requirement it answers", "evidence": "profile entry or resume line"}]}
```

Numbers in `new` must already be in the resume, `skills` or `facts`. Output `replace.json` is `{"replace": [["old", "new"]]}`, HTML-escaped if `--source` is HTML.
