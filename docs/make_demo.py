"""Render docs/demo.gif from real fitcheck output on the fictional example.

Needs Google Chrome and ffmpeg. Set CHROME to the browser binary if it is elsewhere.
"""
import html
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / 'examples'
CHROME = os.environ.get('CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
W, H = 960, 540


def fit(*args, code=0):
    r = subprocess.run([sys.executable, str(ROOT / 'skills/fitcheck/scripts/fitcheck.py'), *args,
                        '--resume', 'resume.txt', '--posting', 'posting.txt', '--reqs', 'reqs.json',
                        '--profile', 'sample-profile.json'], cwd=EX, capture_output=True, text=True)
    assert r.returncode == code, r.stderr
    return r


def span(cls, s):
    return f'<span class="{cls}">{html.escape(s)}</span>'


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        fit('edits', '--edits', 'edits.json', '--out', str(t))
        data = json.loads((t / 'result.json').read_text())
        before, after = data['result'], data['projected']
        edit = json.loads((EX / 'edits.json').read_text())['edits'][0]
        bad = json.loads((EX / 'bad-edits.json').read_text())['edits'][0]
        refused = fit('edits', '--edits', 'bad-edits.json', code=2).stderr.strip().splitlines()

        mark = {'found': ('g', '+ found'), 'addable': ('y', '! missing, profile has evidence'),
                'denied': ('r', '- missing, do not claim'), 'ask': ('y', '? missing, ask the user')}

        def table(res):
            return [f'  {s["name"]:<18}' + span(*mark[s['status']]) for s in res['skills']]

        def head(text):
            return [span('p', '> ') + span('b', text), '']

        def points(label, n, cls):
            return span('b', label) + span(cls + ' big', f'{n}/100')

        pg = next(i for i, s in enumerate(after['skills']) if s['name'] == 'PostgreSQL')
        ask = 'Check this resume against the Frontend Engineer posting'
        scan = head(ask) + [points('Score  ', before['score'], 'y'), ''] + table(before)
        good = head('Add what my profile can back up') + [
            span('d', 'before'), '  ' + html.escape(edit['old']), '',
            span('d', 'after'), '<span class="in">' + html.escape(edit['new']).replace(
                'with the PostgreSQL queries behind them', span('g', 'with the PostgreSQL queries behind them')) + '</span>', '',
            span('d', 'evidence'), '  ' + html.escape(edit['evidence']), '']
        won = good + [points('Score  ', before['score'], 'y') + span('d', '  ->  ') + span('g big', f'{after["score"]}/100'),
                      '', table(after)[pg]]
        lie = head('Now try an edit that makes things up') + [
            '  ' + html.escape(bad['new']).replace('60', span('r', '60')).replace('Kubernetes', span('r', 'Kubernetes')), '']
        no = lie + [span('r b', refused[0])] + [span('r', x) for x in refused[1:]] + ['', span('d', 'Nothing was changed.')]
        end = ['', '', '', span('b huge', 'fitcheck'), span('d', 'Evidence-checked resume matching for Claude Code'), '',
               span('g', 'github.com/taneracar/resume-fitcheck'), '',
               span('d', 'Own scoring formula, not a real ATS score. Fictional resume.')]

        scenes = [(head(ask[:n]), .07) for n in range(4, len(ask), 4)] + [(head(ask), .8)]
        scenes += [(scan[:n], .28) for n in range(3, len(scan))] + [(scan, 3.2)]
        scenes += [(good[:2], .7), (good[:5], 1), (good, 2.8), (won, 2.6), (lie, 2), (no, 4), (end, 3)]

        lst = []
        for i, (lines, secs) in enumerate(scenes):
            body = '\n'.join(lines)
            (t / f'{i}.html').write_text(f'''<meta charset="utf-8"><style>
body{{margin:0;background:#14161b;color:#d7dae0;font:19px/1.45 Menlo,monospace;width:{W}px;height:{H}px;overflow:hidden}}
pre{{margin:0;padding:30px 40px;white-space:pre-wrap;font:inherit}}
.g{{color:#7fd88f}}.y{{color:#f2c661}}.r{{color:#ff7b72}}.d{{color:#8b919d}}.p{{color:#e08a5b}}.b{{font-weight:bold}}
.in{{display:inline-block;padding-left:2ch}}.big{{font-size:24px;font-weight:bold}}.huge{{font-size:46px;line-height:1.5}}</style><pre>{body}</pre>''', encoding='utf-8')
            subprocess.run([CHROME, '--headless', '--disable-gpu', '--hide-scrollbars', f'--window-size={W},{H}',
                            f'--screenshot={t}/{i}.png', f'file://{t}/{i}.html'], check=True, capture_output=True)
            lst.append(f"file '{t}/{i}.png'\nduration {secs}")
        lst.append(f"file '{t}/{len(scenes) - 1}.png'")
        (t / 'list.txt').write_text('\n'.join(lst))
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(t / 'list.txt'), '-vf',
                        'fps=14,split[a][b];[a]palettegen=max_colors=64:stats_mode=full[p];[b][p]paletteuse=dither=none',
                        str(ROOT / 'docs/demo.gif')], check=True)


main()
