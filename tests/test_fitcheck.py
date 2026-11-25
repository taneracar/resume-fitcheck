import copy, io, json, sys, tempfile, unittest, zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'skills' / 'fitcheck' / 'scripts'))
import fitcheck as f
import insights as ins

CV = """Sam Doe
Full Stack Engineer
sam@example.com | (555) 010-0199
EXPERIENCE
Acme 01/2023 - 02/2025
Built 7 production apps with React and TypeScript.
Wrote REST services in Node.js.
EDUCATION
State University | B.S., Computer Science 06/2022
SKILLS
JavaScript, TypeScript, React, Docker, CI/CD
""" + 'Delivered features for client teams in agile cycles with code review. ' * 5
JD = """Full-Stack Engineer. You have 4+ years of experience.
Strong React and TypeScript. Experience with Java, Go or Python.
Bachelor's degree required. Kubernetes is a plus. Must be a U.S. citizen."""
REQS = {'role': 'Full-Stack Engineer', 'company': 'Initech', 'skills': [
    {'name': 'React', 'priority': 'required', 'quote': 'Strong React and TypeScript'},
    {'name': 'Python', 'match': ['Java', 'Go'], 'priority': 'required', 'quote': 'Experience with Java, Go or Python'},
    {'name': 'Kubernetes', 'match': ['k8s'], 'priority': 'preferred', 'quote': 'Kubernetes is a plus'}],
    'years': {'min': 4, 'quote': '4+ years of experience'},
    'degree': {'level': 'bachelor', 'quote': "Bachelor's degree required"},
    'blockers': [{'reason': 'citizenship', 'quote': 'Must be a U.S. citizen'}]}
PROFILE = {'years_experience': 2, 'skills': [{'name': 'Python', 'evidence': 'reports service, 117 tests'}],
           'never_claim': [{'name': 'Kubernetes', 'aliases': ['k8s']}], 'banned_phrases': ['—', 'leverage']}
DOC = {'text': CV, 'pages': None, 'notes': []}
EDIT = {'old': 'Wrote REST services in Node.js.', 'new': 'Wrote REST services in Node.js and Python.', 'evidence': 'reports service'}


class Matching(unittest.TestCase):
    def test_boundaries(self):
        for term, text, n in [('Java', 'JavaScript', 0), ('C', 'C++ and C#', 0), ('C++', 'C++, Rust', 1),
                              ('Go', 'ready to go', 0), ('Go', 'Go, Rust', 1), ('Node.js', 'in Node.js.', 1),
                              ('full stack', 'Full-Stack', 1), ('REST API', 'REST\nAPIs', 1), ('React', 'React.', 1),
                              ('Fullstack', 'full-stack', 1), ('front end', 'Frontend', 1), ('backend', 'back ends', 1), ('.NET', 'C#/.NET', 1), ('CI/CD', 'CI/CD', 1)]:
            self.assertEqual(f.count(term, text), n, (term, text))


class Requirements(unittest.TestCase):
    def bad(self, change):
        r = copy.deepcopy(REQS); change(r)
        with self.assertRaises(f.InputError):
            f.check_reqs(r, JD)

    def test_valid(self):
        f.check_reqs(REQS, JD)

    def test_invented_quote(self):
        self.bad(lambda r: r['skills'][0].update(quote='10 years of React'))

    def test_term_not_in_quote(self):
        self.bad(lambda r: r['skills'][0].update(name='Vue'))

    def test_duplicate(self):
        self.bad(lambda r: r['skills'].append(r['skills'][0]))

    def test_priority_and_empty(self):
        self.bad(lambda r: r['skills'][0].update(priority='must'))
        self.bad(lambda r: r.update(skills=[]))


class Scoring(unittest.TestCase):
    def test_exact_score(self):
        r = f.score(DOC, REQS, PROFILE)
        # required .5*50 + preferred 0 + title 10 + background .75*10 + format 15 = 57.5
        self.assertEqual({k: v['ratio'] for k, v in r['parts'].items()},
                         {'required': .5, 'preferred': 0, 'title': 1, 'background': .75, 'format': 1})
        self.assertEqual(r['score'], 58)
        self.assertEqual([s['status'] for s in r['skills']], ['found', 'addable', 'denied'])

    def test_missing_categories_rescale(self):
        r = copy.deepcopy(REQS)
        r['skills'] = r['skills'][:1]; del r['years'], r['degree']
        self.assertEqual(f.score(DOC, r, {})['score'], 100)

    def test_unknown_skill_asks(self):
        self.assertEqual(f.score(DOC, REQS, {})['skills'][2]['status'], 'ask')

    def test_context_shown(self):
        self.assertIn('with React and', f.score(DOC, REQS, {})['skills'][0]['context'])

    def test_listed_only(self):
        r = {'role': 'x', 'skills': [{'name': 'Docker', 'priority': 'required', 'quote': 'Docker'}]}
        cv = CV.replace('CI/CD\n', 'CI/CD\nPROJECTS\n')
        self.assertTrue(f.score(dict(DOC, text=cv), r, {})['skills'][0]['listed_only'])

    def test_degree(self):
        self.assertEqual(f.degree_rank(CV), 2)
        self.assertEqual(f.degree_rank('EDUCATION\nM.S. in Physics'), 3)
        self.assertEqual(f.degree_rank('EDUCATION\nnone'), 0)

    def test_format(self):
        self.assertEqual(f.score(dict(DOC, text='short'), REQS, {})['parts']['format']['ratio'], 0)
        fails = [c[0] for c in f.format_checks(dict(DOC, text=CV.replace('sam@example.com', '') + '', notes=['uses tables'])) if not c[1]]
        self.assertEqual(fails, ['Email found', 'No broken characters', 'Simple layout'])


class Edits(unittest.TestCase):
    def check(self, **kw):
        src = kw.pop('source', None)
        return f.check_edits({'edits': [dict(EDIT, **kw)]}, CV, REQS, PROFILE, src)

    def test_good_edit_raises_score(self):
        e = self.check()
        after = f.score(dict(DOC, text=f.apply_edits(CV, e)), REQS, PROFILE)
        self.assertEqual(after['score'], 82)

    def test_rejections(self):
        for kw in ({'old': 'not there'}, {'old': 'code review'}, {'evidence': ''},
                   {'new': 'Ran k8s clusters'}, {'new': 'Served 9000 users'},
                   {'new': 'Built services — fast'}, {'new': 'leverage Node.js'}, {'source': '<p>other</p>'}):
            with self.assertRaises(f.InputError, msg=kw):
                self.check(**kw)

    def test_unknown_skill_rejected(self):
        with self.assertRaises(f.InputError):
            f.check_edits({'edits': [EDIT]}, CV, REQS, {})

    def test_any_of_does_not_unlock_siblings(self):
        # evidence for Python must not allow claiming Java from the same any-of requirement
        with self.assertRaises(f.InputError):
            self.check(new='Wrote REST services in Java.')

    def test_known_number_ok_and_source_entities(self):
        self.check(new='Wrote 117 REST tests', source='<p>Wrote REST services in Node.js.</p>')


class Insights(unittest.TestCase):
    def status(self, checks):
        return {n: s for n, s, _ in checks}

    def run_on(self, cv, **kw):
        d = ins.analyse('cv.txt', dict(DOC, text=cv), dict(REQS, **kw), JD)
        return {k: self.status(d[k]) for k in ('Searchability', 'Recruiter tips', 'Formatting')}, d

    def test_searchability(self):
        s = self.run_on(CV)[0]['Searchability']
        self.assertEqual([k for k, v in s.items() if v == 'CHECK'], ['File type', 'Location', 'Summary section'])
        s = self.run_on('Sam Doe\nPortland, OR\nSUMMARY\nx\n' + CV.replace('06/2022', 'June 2022'))[0]['Searchability']
        self.assertEqual((s['Location'], s['Summary section'], s['One date format']), ('PASS', 'PASS', 'CHECK'))

    def test_month_in_prose_is_not_a_format_problem(self):
        s = self.run_on(CV + ' Launched in October 2026.')[0]['Searchability']
        self.assertEqual(s['One date format'], 'PASS')

    def test_results_ignore_dates_and_versions(self):
        n = lambda t: len(ins.results_lines({'experience': t}))
        self.assertEqual(n('Acme 01/2023 - 2025. Used Next.js 16 and PostgreSQL 17.'), 0)
        self.assertEqual(n('Cut load time by 30%. Built 7 apps.'), 2)

    def test_tips(self):
        t = self.run_on(CV + '\nResponsible for my team. Team player.')[0]['Recruiter tips']
        self.assertEqual((t['No cliches'], t['No weak openers'], t['No first person'], t['Web presence'], t['Job level']),
                         ('CHECK', 'CHECK', 'CHECK', 'CHECK', 'N/A'))
        self.assertEqual(self.run_on(CV, role='Senior Engineer')[0]['Recruiter tips']['Job level'], 'CHECK')

    def test_soft_is_reported_but_not_scored(self):
        soft = REQS['skills'] + [{'name': 'ownership', 'priority': 'soft', 'quote': 'x'}]
        self.assertEqual(f.score(DOC, dict(REQS, skills=soft), PROFILE)['score'], 58)
        self.assertEqual(self.run_on(CV, skills=soft)[1]['soft'][0]['found'], False)

    def test_counts(self):
        r = f.score(DOC, REQS, {}, JD)['skills'][0]
        self.assertEqual((r['resume_count'], r['posting_count']), (2, 1))


class Files(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)

    def docx(self, body, prefix=''):
        p = self.d / 'a.docx'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('word/document.xml', prefix + f'<w:document xmlns:w="{f.W[1:-1]}"><w:body>{body}</w:body></w:document>')
        return p

    def test_docx(self):
        d = f.read_resume(self.docx('<w:tbl/><w:p><w:r><w:t>Hel</w:t></w:r><w:r><w:t>lo</w:t></w:r></w:p>'))
        self.assertEqual((d['text'], d['notes']), ('Hello', ['uses tables']))

    def test_docx_dtd_refused(self):
        with self.assertRaises(f.InputError):
            f.read_resume(self.docx('', '<!DOCTYPE x>'))

    def test_bad_files(self):
        for n in ('x.rtf', 'x.docx', 'x.pdf'):
            (self.d / n).write_text('nope')
            with self.assertRaises(f.InputError):
                f.read_resume(self.d / n)

    def test_cli(self):
        w = lambda n, s: ((self.d / n).write_text(s if isinstance(s, str) else json.dumps(s)), str(self.d / n))[1]
        args = ['--resume', w('cv.txt', CV), '--posting', w('jd.txt', JD), '--reqs', w('r.json', REQS), '--profile', w('p.json', PROFILE)]
        out = self.d / 'out'
        with redirect_stdout(io.StringIO()) as s:
            self.assertEqual(f.main(['edits', *args, '--edits', w('e.json', {'edits': [EDIT]}), '--out', str(out)]), 0)
        self.assertIn('58/100** (with edits: 82/100)', s.getvalue())
        self.assertIn('BLOCKER: citizenship', s.getvalue())
        self.assertEqual(json.loads((out / 'replace.json').read_text())['replace'], [[EDIT['old'], EDIT['new']]])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(f.main(['scan', *args[:-1], str(self.d / 'none.json')]), 2)


if __name__ == '__main__':
    unittest.main()
