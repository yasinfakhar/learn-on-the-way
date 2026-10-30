import hashlib, os, re
from pathlib import Path
import yaml

ROOT = Path(os.getenv('COURSES_DIR', 'courses'))
def load(course_id):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', course_id):
        raise ValueError('Invalid course ID')
    path = ROOT / f'{course_id}.md'
    if not path.exists(): raise ValueError('Course not found')
    raw = path.read_text()
    _, header, body = raw.split('---', 2)
    meta = yaml.safe_load(header)
    if meta.get('id') != course_id: raise ValueError('Course ID does not match filename')
    steps = []
    for part in re.split(r'^## Step ', body, flags=re.M)[1:]:
        heading, content = part.split('\n', 1)
        match = re.fullmatch(r'(\d+) \[(text|qa|quiz)\] (.+)', heading.strip())
        if not match or int(match[1]) != len(steps)+1: raise ValueError('Invalid step heading or order')
        item = {'number': int(match[1]), 'type': match[2], 'title': match[3], 'content': content.strip()}
        if item['type'] == 'quiz':
            question, sep, answer = content.partition('\n### Expected answer\n')
            if not sep or not answer.strip(): raise ValueError('Quiz needs an expected answer')
            item.update(content=question.strip(), expected_answer=answer.strip())
        steps.append(item)
    if not steps: raise ValueError('Course has no steps')
    return {'id': course_id, 'name': str(meta['name']), 'description': str(meta['description']),
            'version': hashlib.sha256(raw.encode()).hexdigest(), 'step_count': len(steps), 'steps': steps}
def catalog(query=''):
    courses = [load(p.stem) for p in sorted(ROOT.glob('*.md'))]
    return [{k:v for k,v in c.items() if k != 'steps'} for c in courses
            if query.casefold() in (' '.join([c['name'], c['description']] + [s['content'] for s in c['steps']])).casefold()]
