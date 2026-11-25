"""Recruiter-style checks reported beside the score. None of these change the score.

Each check is (name, status, detail), status one of PASS, CHECK, N/A.
"""
import re
import subprocess
from pathlib import Path

import fitcheck as f

CLICHES = ['team player', 'hard worker', 'hard-working', 'go-getter', 'self-starter', 'detail-oriented',
           'results-driven', 'results-oriented', 'think outside the box', 'synergy', 'passionate', 'dynamic',
           'guru', 'ninja', 'rockstar', 'proven track record', 'fast-paced', 'cutting-edge', 'spearheaded']
WEAK = ['responsible for', 'duties included', 'worked on', 'helped with', 'assisted with', 'tasked with']
LEVELS = [('intern', 0, r'intern(ship)?'), ('entry', 1, r'junior|jr\.?|entry[ -]level|associate|new grad'),
          ('senior', 3, r'senior|sr\.?'), ('lead', 4, r'staff|principal|lead|director|head of|vp')]
DATE = (r'\b\d{1,2}/\d{4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{4}\b')


def ok(name, passed, detail=''):
    return (name, 'PASS' if passed else 'CHECK', detail)


def results_lines(secs):
    """Sentences in experience and projects that carry a number other than a date."""
    body = f.flat(secs.get('experience', '') + '\n' + secs.get('projects', ''))
    body = re.sub(DATE + r'|\b(?:19|20)\d\d\b', ' ', body, flags=re.I)
    # digits glued to a name (Next.js 16, PostgreSQL 17, B2B) are versions, not results
    body = re.sub(r'\b(?:[A-Z][\w.]*(?:js|SQL)|iOS|Python|Java|Node|React|Android)\s+\d+(\.\d+)*\b|\b[A-Za-z]+\d\w*', ' ', body)
    return [s for s in re.split(r'(?<=[.;])\s+', body) if re.search(r'\d', s)]


def file_info(path):
    """Facts about a PDF from poppler; empty when a tool is missing."""
    def run(*cmd):
        try:
            r = subprocess.run([*cmd, str(Path(path).resolve())], capture_output=True, timeout=60)
            return r.stdout.decode('utf-8', 'replace') if r.returncode == 0 else ''
        except (OSError, subprocess.TimeoutExpired):
            return ''
    info = {}
    m = re.search(r'Page size:\s+([\d.]+) x ([\d.]+)', run('pdfinfo'))
    if m:
        size = (round(float(m[1])), round(float(m[2])))
        info['page'] = {(612, 792): 'US Letter', (595, 842): 'A4'}.get(size, f'{size[0]} x {size[1]} pt')
    rows = run('pdffonts').splitlines()[2:]
    if rows:
        fonts = {re.sub(r'^[A-Z]{6}\+', '', r.split()[0]) for r in rows if r.split()}
        info['fonts'] = sorted({re.split(r'[-,]', x)[0] for x in fonts})
        # columns after the encoding: emb sub uni object ID
        info['unmapped'] = sum(1 for r in rows if re.search(r'\b(yes|no)\s+(yes|no)\s+no\s+\d+\s+\d+\s*$', r))
    out = run('pdfimages', '-list').splitlines()
    if out:
        info['images'] = len(out[2:])
    return info


def searchability(path, text, secs, reqs):
    low, top = f.clean(text).lower(), secs['top']
    # only date ranges and education dates; a month named in a sentence is not a format problem
    ranges = re.findall(r'(?:' + DATE + r')\s*(?:-|to)\s*(?:' + DATE + r'|present|current|now)', low)
    dates = re.findall(DATE, ' '.join(ranges) + '\n' + secs.get('education', '').lower())
    slash = sum('/' in d for d in dates)
    name = Path(path).name
    return [
        ok('File type', Path(path).suffix.lower() in ('.pdf', '.docx'), Path(path).suffix),
        ok('File name', bool(re.fullmatch(r'[\w.\- ]+', name)) and len(name) <= 80, name),
        ok('Exact job title', f.count(reqs['role'], text) > 0, reqs['role']),
        ok('Email', bool(re.search(r'[\w.+-]+@[\w-]+\.\w+', top)), 'before the first heading'),
        ok('Phone', bool(re.search(r'\+?\d[\d\s().-]{8,}\d', top)), 'before the first heading'),
        ok('Location', bool(re.search(r'\b[A-Z][\w. ]+, (?:[A-Z]{2}\b|[A-Z][a-z]+)', top)), 'city and state or country'),
        ok('Summary section', 'summary' in secs),
        ok('Experience section', 'experience' in secs),
        ok('Education section', 'education' in secs),
        ok('Skills section', 'skills' in secs),
        ok('One date format', len(dates) > 0 and slash in (0, len(dates)), f'{len(dates)} dates in ranges and education'),
    ]


def recruiter_tips(text, secs, posting, reqs):
    low = f.clean(text).lower()
    words, results = len(text.split()), results_lines(secs)
    cliches = [c for c in CLICHES if f.count(c, low)]
    weak = [w for w in WEAK if f.count(w, low)]
    me = len(re.findall(r"\b(?:I|I'm|I've|my|me)\b", f.clean(text)))
    level = [(n, r) for n, r, rx in LEVELS if re.search(r'(?<!\w)(?:' + rx + r')(?!\w)', f.clean(reqs['role']), re.I)]
    cv_head = secs['top'].lower()
    if level:
        n, _ = max(level, key=lambda x: x[1])
        rx = next(x[2] for x in LEVELS if x[0] == n)
        lvl = ok('Job level', bool(re.search(r'(?<!\w)(?:' + rx + r')(?!\w)', cv_head + secs.get('experience', '').lower())),
                 f'posting title says {n}')
    else:
        lvl = ('Job level', 'N/A', 'posting title names no level')
    links = [k for k, rx in (('LinkedIn', r'linkedin\.com/in/'), ('GitHub', r'github\.com/'),
                             ('website', r'\b(?!linkedin|github)[\w-]+\.(?:dev|app|io|me|com|net|org)\b')) if re.search(rx, re.sub(r'\S+@\S+', '', low))]
    return [
        lvl,
        ok('Measurable results', len(results) >= 5, f'{len(results)} (aim for 5+)'),
        ok('Word count', 400 <= words <= 1000, f'{words} (aim for 400-1000)'),
        ok('Web presence', bool(links), ', '.join(links)),
        ok('No cliches', not cliches, ', '.join(cliches)),
        ok('No weak openers', not weak, ', '.join(weak)),
        ok('No first person', me == 0, f'{me} found' if me else ''),
    ]


def formatting(path, doc):
    info = file_info(path) if Path(path).suffix.lower() == '.pdf' else {}
    out = []
    if doc['pages']:
        out.append(ok('Page count', doc['pages'] <= 2, str(doc['pages'])))
    if 'page' in info:
        out.append(ok('Page size', info['page'] in ('US Letter', 'A4'), info['page']))
    if 'fonts' in info:
        out.append(ok('Font families', len(info['fonts']) <= 2, ', '.join(info['fonts'])))
        out.append(ok('Fonts map to text', info['unmapped'] == 0))
    if 'images' in info:
        out.append(ok('No images', info['images'] == 0, str(info['images']) if info['images'] else ''))
    out.append(ok('No tables or text boxes', not doc['notes'], ', '.join(doc['notes'])))
    return out


def analyse(path, doc, reqs, posting):
    secs = f.sections(doc['text'])
    soft = []
    for s in reqs['skills']:
        if s['priority'] == 'soft':
            hits = [t for t in f.terms(s) if f.count(t, doc['text'])]
            soft.append({'name': s['name'], 'found': bool(hits), 'quote': s['quote'],
                         'context': f.context(hits[0], doc['text']) if hits else ''})
    return {'Searchability': searchability(path, doc['text'], secs, reqs),
            'Recruiter tips': recruiter_tips(doc['text'], secs, posting, reqs),
            'Formatting': formatting(path, doc), 'soft': soft}
