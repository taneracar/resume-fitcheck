#!/usr/bin/env python3
"""Score a resume against a job posting. Standard library only (PDFs need pdftotext).

  fitcheck.py extract RESUME
  fitcheck.py scan  --resume R --posting JD.txt --reqs reqs.json [--profile P] [--out DIR]
  fitcheck.py edits --resume R --posting JD.txt --reqs reqs.json --profile P --edits edits.json
                    [--source resume.html] [--out DIR]

The score is fitcheck's own formula. It does not reproduce any real ATS.
"""
import argparse
import html
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WEIGHTS = {'required': 50, 'preferred': 15, 'title': 10, 'background': 10, 'format': 15}
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MAX_XML = 20_000_000
HEADINGS = {
    'summary': r'(professional )?(summary|profile)|about( me)?',
    'experience': r'((work|professional|relevant) )?(experience|history)|employment( history)?',
    'projects': r'((selected|personal) )?projects',
    'education': r'education( and training)?',
    'skills': r'((technical|core) )?skills( (and|&) tools)?|technologies',
}
DEGREES = [
    ('doctorate', 4, r"ph\.?d\.?|doctorate|doctor of"),
    ('master', 3, r"master'?s?( degree| of)|m\.s\.?|msc|mba"),
    ('bachelor', 2, r"bachelor'?s?|b\.s\.?|b\.a\.?|bsc|bs in|ba in"),
    ('associate', 1, r"associate'?s? (degree|of)|a\.s\.?"),
]
TITLE_NOISE = {'a', 'and', 'of', 'the', 'i', 'ii', 'iii', 'iv', 'jr', 'sr', 'junior', 'senior',
               'staff', 'lead', 'associate', 'remote', 'hybrid', 'in', 'for'}


class InputError(Exception):
    pass


# ---------- text ----------

def clean(text):
    text = unicodedata.normalize('NFKC', text)
    for a, b in (('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"'), ('­', ''), ('​', '')):
        text = text.replace(a, b)
    return re.sub(r'[‐‑‒–—]', '-', text)


def flat(text):
    return re.sub(r'\s+', ' ', clean(text)).strip()


def split_compounds(text):
    return re.sub(r'\b(full|front|back)[\s-]?(stack|end)(?=\b|s\b)', r'\1 \2', text, flags=re.I)


def context(term, text, width=35):
    text = split_compounds(flat(text))
    m = term_re(term).search(text)
    return '' if not m else '...' + text[max(0, m.start() - width):m.end() + width].strip() + '...'


def term_re(term):
    """Whole-term match: 'Java' misses JavaScript, 'C' misses C++ and C#.

    Spaces, hyphens and slashes are interchangeable ('full stack' = 'full-stack').
    One- and two-letter terms keep their case, so 'Go' does not match 'go'.
    """
    term = split_compounds(clean(term).strip())
    parts = [re.escape(p) for p in re.split(r'[\s\-/]+', term) if p]
    body = r'[\s\-/]+'.join(parts)
    if len(term) > 3 and term[-1].isalpha() and not term.lower().endswith('s'):
        body += 's?'
    flags = 0 if len(term) <= 2 else re.I
    return re.compile(r'(?<![\w.+#])' + body + r'(?![\w+#])', flags)


def count(term, text):
    return len(term_re(term).findall(split_compounds(clean(text)))) if term.strip() else 0


def sections(text):
    out, current = {'top': []}, 'top'
    for line in clean(text).splitlines():
        bare = line.strip().strip(':').lower()
        hit = next((k for k, rx in HEADINGS.items() if re.fullmatch(rx, bare)), None)
        if hit:
            current = hit
            out.setdefault(hit, [])
        else:
            out[current].append(line)
    return {k: '\n'.join(v) for k, v in out.items()}


# ---------- reading files ----------

def docx_part(z, name):
    if z.getinfo(name).file_size > MAX_XML:
        raise InputError(f'{name} is too large')
    raw = z.read(name)
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
        raise InputError(f'{name} declares a DTD, refusing to parse it')
    root = ET.fromstring(raw)
    lines = []
    for p in root.iter(W + 'p'):
        line = ''
        for n in p.iter():
            if n.tag == W + 't':
                line += n.text or ''
            elif n.tag == W + 'tab':
                line += '\t'
            elif n.tag in (W + 'br', W + 'cr'):
                line += '\n'
        lines.append(line)
    return root, '\n'.join(lines)


def read_resume(path):
    """Return {text, pages, notes}; notes are layout risks found in the file itself."""
    path = Path(path)
    if not path.is_file():
        raise InputError(f'no such file: {path}')
    kind, notes, pages = path.suffix.lower(), [], None
    if kind == '.pdf':
        try:
            r = subprocess.run(['pdftotext', '-enc', 'UTF-8', str(path.resolve()), '-'],
                               capture_output=True, timeout=60)
        except FileNotFoundError:
            raise InputError('pdftotext not found (macOS: brew install poppler, '
                             'Debian/Ubuntu: apt install poppler-utils)')
        except subprocess.TimeoutExpired:
            raise InputError('pdftotext timed out on this PDF')
        if r.returncode:
            raise InputError('cannot read PDF: ' + r.stderr.decode(errors='replace').strip()[:200])
        text = r.stdout.decode('utf-8', 'replace')
        pages = text.count('\f')
        text = text.replace('\f', '\n')
    elif kind == '.docx':
        try:
            with zipfile.ZipFile(path) as z:
                root, text = docx_part(z, 'word/document.xml')
                if root.find('.//' + W + 'tbl') is not None:
                    notes.append('uses tables')
                if root.find('.//' + W + 'txbxContent') is not None:
                    notes.append('uses text boxes')
                for n in z.namelist():
                    if re.fullmatch(r'word/(header|footer)\d*\.xml', n):
                        if '@' in docx_part(z, n)[1]:
                            notes.append('contact details in header or footer')
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
            raise InputError(f'cannot read DOCX: {e}')
    elif kind in ('.txt', '.md'):
        text = path.read_text(encoding='utf-8')
    else:
        raise InputError(f'unsupported file type {kind or "(none)"}: use PDF, DOCX, TXT or MD')
    return {'text': text, 'pages': pages, 'notes': sorted(set(notes))}


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise InputError(f'{path}: {e}')
    if not isinstance(data, dict):
        raise InputError(f'{path}: expected a JSON object')
    return data


# ---------- requirements ----------

def check_reqs(reqs, posting):
    """Every requirement must be anchored to a verbatim quote from the posting."""
    errors, jd, seen = [], flat(posting).lower(), set()

    def quoted(item, where):
        q = flat(str(item.get('quote') or '')).lower()
        if not q:
            errors.append(f'{where}: missing quote')
        elif q not in jd:
            errors.append(f'{where}: quote is not in the posting')

    if not reqs.get('role'):
        errors.append('role is missing')
    for s in reqs.get('skills', []):
        name = s.get('name', '?')
        if name.lower() in seen:
            errors.append(f'skill {name}: listed twice')
        seen.add(name.lower())
        if s.get('priority') not in ('required', 'preferred', 'soft'):
            errors.append(f'skill {name}: priority must be required, preferred or soft')
        quoted(s, f'skill {name}')
        if not any(count(t, str(s.get('quote', ''))) for t in terms(s)):
            errors.append(f'skill {name}: none of its terms appear in its quote')
    if not any(s.get('priority') != 'soft' for s in reqs.get('skills', [])):
        errors.append('no required or preferred skills listed')
    years, degree = reqs.get('years'), reqs.get('degree')
    if years:
        quoted(years, 'years')
        if not isinstance(years.get('min'), (int, float)) or years['min'] < 0:
            errors.append('years: min must be a number >= 0')
    if degree:
        quoted(degree, 'degree')
        if degree.get('level') not in [d[0] for d in DEGREES]:
            errors.append('degree: level must be associate, bachelor, master or doctorate')
    for b in reqs.get('blockers', []):
        quoted(b, f'blocker {b.get("reason", "?")}')
    if errors:
        raise InputError('requirements rejected:\n  ' + '\n  '.join(errors))


def terms(skill):
    return [t for t in [skill.get('name', '')] + list(skill.get('match', [])) if t]


# ---------- scoring ----------

def format_checks(doc):
    text, low = clean(doc['text']), clean(doc['text']).lower()
    words, secs = len(text.split()), sections(text)
    if words < 50:
        return [('Text can be extracted', False, WEIGHTS['format'], f'{words} words; scanned image?')]
    bad = len(re.findall(r'[�-]|\(cid:\d+\)', doc['text']))
    dates = re.findall(r'\b(?:\d{1,2}/\d{4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{4}|(?:19|20)\d\d)\b', low)
    checks = [
        ('Text can be extracted', True, 0, f'{words} words'),
        ('Email found', bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', text)), 3, ''),
        ('Phone found', bool(re.search(r'\+?\d[\d\s().-]{8,}\d', text)), 2, ''),
        ('Experience heading', 'experience' in secs, 2, ''),
        ('Education heading', 'education' in secs, 2, ''),
        ('Skills heading', 'skills' in secs, 2, ''),
        ('Dates found', len(dates) >= 2, 1, ''),
        ('No broken characters', bad == 0, 2, f'{bad} found' if bad else ''),
        ('Length', words <= 1200 and (doc['pages'] or 1) <= 2, 1,
         f'{words} words' + (f', {doc["pages"]} page(s)' if doc['pages'] else '')),
        ('Simple layout', not doc['notes'], 2, ', '.join(doc['notes'])),
    ]
    return checks


def degree_rank(text):
    secs = sections(text)
    area = secs.get('education') or text
    return max([r for _, r, rx in DEGREES if re.search(r'(?<![\w.])(?:' + rx + r')(?!\w)', area, re.I)] or [0])


def score(doc, reqs, profile, posting=''):
    text = doc['text']
    secs = sections(text)
    body = '\n'.join(v for k, v in secs.items() if k != 'skills')
    rows = []
    for s in reqs['skills']:
        if s['priority'] == 'soft':
            continue
        hits = [t for t in terms(s) if count(t, text)]
        rows.append({
            'name': s['name'], 'priority': s['priority'], 'found': bool(hits), 'matched': hits,
            'resume_count': sum(count(t, text) for t in set(terms(s))),
            'posting_count': sum(count(t, posting) for t in set(terms(s))),
            'context': context(hits[0], body) or context(hits[0], text) if hits else '',
            'listed_only': bool(hits) and not any(count(t, body) for t in hits),
            'status': 'found' if hits else profile_status(s, profile), 'quote': s['quote'],
        })
    parts = {}
    for p in ('required', 'preferred'):
        group = [r for r in rows if r['priority'] == p]
        if group:
            parts[p] = sum(r['found'] for r in group) / len(group)

    if count(reqs['role'], text):
        parts['title'] = 1.0
    else:
        want = set(re.findall(r'[a-z+#]+', split_compounds(clean(reqs['role'])).lower())) - TITLE_NOISE
        lines = [set(re.findall(r'[a-z+#]+', l.lower())) for l in split_compounds(clean(text)).splitlines()]
        if want:
            parts['title'] = max([len(want & l) / len(want) for l in lines] or [0])

    back = []
    have = profile.get('years_experience')
    if reqs.get('years') and have is not None:
        need = reqs['years']['min']
        back.append(1.0 if need == 0 else min(have / need, 1.0))
    if reqs.get('degree'):
        need = next(r for n, r, _ in DEGREES if n == reqs['degree']['level'])
        back.append(1.0 if degree_rank(text) >= need else 0.0)
    if back:
        parts['background'] = sum(back) / len(back)

    checks = format_checks(doc)
    lost = sum(c[2] for c in checks if not c[1])
    parts['format'] = max(0, WEIGHTS['format'] - lost) / WEIGHTS['format']
    # Categories the posting says nothing about are left out and the rest rescaled to 100.
    total = sum(WEIGHTS[k] for k in parts)
    return {'score': round(100 * sum(WEIGHTS[k] * v for k, v in parts.items()) / total),
            'parts': {k: {'ratio': round(v, 3), 'weight': round(100 * WEIGHTS[k] / total, 1)}
                      for k, v in parts.items()},
            'skills': rows, 'format': checks}


def profile_status(skill, profile):
    """addable = evidence on file, denied = user said no, ask = nothing known."""
    names = {clean(t).lower() for t in terms(skill)}

    def same(entry):
        return names & {clean(t).lower() for t in [entry['name']] + entry.get('aliases', [])}
    if any(same(e) for e in profile.get('never_claim', [])):
        # an any-of requirement can still be met by another of its terms
        if not any(same(e) and e.get('evidence') for e in profile.get('skills', [])):
            return 'denied'
    if any(same(e) and e.get('evidence') for e in profile.get('skills', [])):
        return 'addable'
    return 'ask'


# ---------- edits ----------

def check_edits(data, resume_text, reqs, profile, source=None):
    """Reject edits that cannot be applied or that claim something without evidence."""
    edits = data.get('edits')
    if not isinstance(edits, list) or not edits:
        raise InputError('edits.json needs a non-empty "edits" list')
    errors, text = [], flat(resume_text)
    evidence = flat(json.dumps([s for s in profile.get('skills', []) if s.get('evidence')], ensure_ascii=False) + ' '
                    + json.dumps(profile.get('facts', []), ensure_ascii=False))
    known = set(re.findall(r'\d[\d,.]*\d|\d', text + ' ' + evidence))
    for i, e in enumerate(edits, 1):
        if not isinstance(e, dict):
            errors.append(f'edit {i}: must be an object')
            continue
        old, new = flat(str(e.get('old', ''))), flat(str(e.get('new', '')))
        if not old or not new:
            errors.append(f'edit {i}: needs old and new')
            continue
        if not str(e.get('evidence', '')).strip():
            errors.append(f'edit {i}: needs evidence')
        if text.count(old) != 1:
            errors.append(f'edit {i}: old text found {text.count(old)} times in the resume, expected 1')
        if source is not None and source.count(str(e['old'])) != 1:
            errors.append(f'edit {i}: old text found {source.count(str(e["old"]))} times in the source file, expected 1')
        for n in profile.get('never_claim', []):
            for t in [n['name']] + n.get('aliases', []):
                if count(t, new) and not count(t, old):
                    errors.append(f'edit {i}: adds "{t}", which the profile says never to claim')
        for s in reqs.get('skills', []):
            for t in terms(s):
                if count(t, new) and not count(t, resume_text) and not count(t, evidence):
                    errors.append(f'edit {i}: adds "{t}" with no evidence in the resume or profile')
        for num in re.findall(r'\d[\d,.]*\d|\d', new):
            if num not in known:
                errors.append(f'edit {i}: number {num} is not in the resume or profile')
        for b in profile.get('banned_phrases', []):
            # checked on the raw text: flat() turns dashes into hyphens
            if b.lower() in str(e['new']).lower() and b.lower() not in str(e['old']).lower():
                errors.append(f'edit {i}: banned phrase "{b}"')
    if errors:
        raise InputError('edits rejected:\n  ' + '\n  '.join(dict.fromkeys(errors)))
    return edits


def apply_edits(text, edits):
    """Apply to extracted text, tolerating line wraps inside the old text."""
    text = clean(text)
    for e in edits:
        rx = r'\s+'.join(re.escape(w) for w in flat(e['old']).split())
        text, n = re.subn(rx, lambda _: flat(e['new']), text, count=1)
        if not n:
            raise InputError(f'edits overlap: "{e["old"][:50]}" is gone after an earlier edit')
    return text


# ---------- report ----------

def cell(s):
    return flat(str(s)).replace('|', '\\|')


def report(result, reqs, projected=None, edits=None, extra=None):
    L = [f'# fitcheck: {cell(reqs["role"])}' + (f', {cell(reqs["company"])}' if reqs.get('company') else ''), '']
    for b in reqs.get('blockers', []):
        L.append(f'> **BLOCKER: {cell(b["reason"])}.** "{cell(b["quote"])}"')
    if reqs.get('blockers'):
        L.append('')
    L.append(f'**Score: {result["score"]}/100**' + (f' (with edits: {projected["score"]}/100)' if projected else ''))
    L += ['', "This is fitcheck's own formula, not a real ATS score.", '',
          '| Part | Match | Weight |', '|---|---|---|']
    for k, v in result['parts'].items():
        L.append(f'| {k} | {v["ratio"]:.0%} | {v["weight"]:g} |')
    label = {'found': 'found', 'addable': 'missing, profile has evidence', 'denied': 'missing, do not claim',
             'ask': 'missing, ask the user'}
    for p in ('required', 'preferred'):
        rows = [r for r in result['skills'] if r['priority'] == p]
        if rows:
            L += ['', f'## {p.capitalize()} skills', '', '| Skill | Status | Resume | Posting | Resume says | Posting says |', '|---|---|---|---|---|---|']
            for r in rows:
                s = label[r['status']] + (' (skills list only)' if r['listed_only'] else '')
                L.append(f'| {cell(r["name"])} | {s} | {r["resume_count"]}x | {r["posting_count"]}x | {cell(r["context"])} | {cell(r["quote"])} |')
    if extra:
        if extra['soft']:
            L += ['', '## Soft skills (not scored)', '', '| Skill | Status | Resume says | Posting says |', '|---|---|---|---|']
            L += [f'| {cell(s["name"])} | {"found" if s["found"] else "missing"} | {cell(s["context"])} | {cell(s["quote"])} |'
                  for s in extra['soft']]
        for title in ('Searchability', 'Recruiter tips', 'Formatting'):
            todo = sum(c[1] == 'CHECK' for c in extra[title])
            L += ['', f'## {title} (not scored): ' + (f'{todo} to check' if todo else 'all clear'), '']
            L += [f'- {st} {n}' + (f': {cell(d)}' if d else '') for n, st, d in extra[title]]
    L += ['', '## Format (scored)', '']
    L += [f'- {"PASS" if ok else "FAIL"} {n}' + (f': {d}' if d else '') for n, ok, _, d in result['format']]
    if edits:
        L += ['', '## Suggested edits']
        for i, e in enumerate(edits, 1):
            L += ['', f'**{i}.** {cell(e.get("why", ""))}', '', f'- Before: {flat(e["old"])}',
                  f'- After: {flat(e["new"])}', f'- Evidence: {flat(e["evidence"])}']
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description='Score a resume against a job posting.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('extract').add_argument('resume')
    for name in ('scan', 'edits'):
        p = sub.add_parser(name)
        for a in ('resume', 'posting', 'reqs'):
            p.add_argument('--' + a, required=True)
        p.add_argument('--profile', required=name == 'edits')
        p.add_argument('--out')
        if name == 'edits':
            p.add_argument('--edits', required=True)
            p.add_argument('--source', help='editable resume (HTML/text) the edits will be applied to')
    a = ap.parse_args(argv)
    try:
        doc = read_resume(a.resume)
        if a.cmd == 'extract':
            print(doc['text'])
            return 0
        posting = Path(a.posting).read_text(encoding='utf-8')
        reqs = load(a.reqs)
        profile = load(a.profile) if a.profile else {}
        check_reqs(reqs, posting)
        result, projected, edits = score(doc, reqs, profile, posting), None, None
        if a.cmd == 'edits':
            source = Path(a.source).read_text(encoding='utf-8') if a.source else None
            is_html = bool(a.source) and Path(a.source).suffix.lower() in ('.html', '.htm')
            if is_html:
                source = html.unescape(source)
            edits = check_edits(load(a.edits), doc['text'], reqs, profile, source)
            projected = score(dict(doc, text=apply_edits(doc['text'], edits)), reqs, profile, posting)
        import insights  # imports this module, so only once it is loaded
        extra = insights.analyse(a.resume, doc, reqs, posting)
        md = report(result, reqs, projected, edits, extra)
        print(md)
        if a.out:
            out = Path(a.out).expanduser()
            out.mkdir(parents=True, exist_ok=True)
            (out / 'report.md').write_text(md, encoding='utf-8')
            (out / 'result.json').write_text(json.dumps(
                {'result': result, 'projected': projected, 'insights': extra}, indent=2, ensure_ascii=False), encoding='utf-8')
            if edits:
                def enc(s):
                    return html.escape(s, quote=False) if is_html else s
                pairs = [[enc(e['old']), enc(e['new'])] for e in edits]
                (out / 'replace.json').write_text(json.dumps(
                    {'replace': pairs}, indent=2, ensure_ascii=False), encoding='utf-8')
        return 0
    except (InputError, OSError, UnicodeDecodeError) as e:
        print(f'fitcheck: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
