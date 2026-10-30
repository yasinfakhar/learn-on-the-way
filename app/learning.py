import json, uuid
from sqlalchemy import select
from .db import Session, Progress
from .courses import load, catalog

TOOLS = {
 'list_micro_courses': {'description': 'List course IDs, names, descriptions and step counts.', 'properties': {}},
 'search_micro_courses': {'description': 'Search titles, descriptions and course material.', 'properties': {'query': {'type':'string'}}, 'required':['query']},
 'start_or_continue_course': {'description': 'Start or resume your course at the first incomplete step.', 'properties': {'course_id': {'type':'string'}}, 'required':['course_id']},
 'open_step': {'description': 'Read a course step and its teaching material. Opening does not complete it.', 'properties': {'course_id': {'type':'string'}, 'step': {'type':'integer','minimum':1}}, 'required':['course_id','step']},
 'record_answer': {'description': 'Record whether the learner answered a quiz, their exact answer and optional correctness. Never invent an answer.', 'properties': {'course_id': {'type':'string'}, 'step': {'type':'integer','minimum':1}, 'answered': {'type':'boolean'}, 'answer': {'type':'string','maxLength':10000}, 'correct': {'type':['boolean','null']}}, 'required':['course_id','step','answered','answer']},
 'complete_step': {'description': 'Complete a step after delivery or discussion; quizzes require a recorded answer.', 'properties': {'course_id': {'type':'string'}, 'step': {'type':'integer','minimum':1}}, 'required':['course_id','step']},
 'complete_course': {'description': 'Mark your course passed after all steps are complete.', 'properties': {'course_id': {'type':'string'}}, 'required':['course_id']},
 'rate_course': {'description': 'Rate your passed course from 1 to 5.', 'properties': {'course_id': {'type':'string'}, 'rating': {'type':'integer','minimum':1,'maximum':5}}, 'required':['course_id','rating']},
 'get_my_learning': {'description': 'List only your started and passed courses, answers, progress and ratings.', 'properties': {}},
}
def execute(user_id, name, args):
    if name == 'list_micro_courses': return catalog()
    if name == 'search_micro_courses': return catalog(args['query'])
    with Session.begin() as db:
        if name == 'get_my_learning':
            return [{'course_id':p.course_id, **json.loads(p.data)} for p in db.scalars(select(Progress).where(Progress.user_id == user_id))]
        course = load(args['course_id'])
        # Serialize mutations per learner/course to prevent concurrent lost updates.
        if db.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key':user_id+':'+course['id']})
        p = db.scalar(select(Progress).where(Progress.user_id == user_id, Progress.course_id == course['id']).with_for_update())
        if p is None:
            if name != 'start_or_continue_course': raise ValueError('Start this course first')
            p = Progress(id=str(uuid.uuid4()), user_id=user_id, course_id=course['id'], version=course['version'], data='{}')
            db.add(p)
        if p.version != course['version']: raise ValueError('Course material changed. Administrator must migrate progress before continuing.')
        data = json.loads(p.data)
        data.setdefault('completed_steps', [])
        data.setdefault('answers', {})
        data.setdefault('status', 'started')
        step = args.get('step')
        item = None
        if step is not None:
            if step < 1 or step > course['step_count']: raise ValueError('Step out of range')
            item = course['steps'][step-1]
        if name == 'open_step': return {'step':item, 'course_material':course['steps'], 'progress':data}
        if name == 'record_answer':
            if item['type'] != 'quiz': raise ValueError('This step is not a quiz')
            if args['answered'] and not args['answer'].strip(): raise ValueError('An answered question requires the actual answer')
            if not args['answered'] and args['answer'].strip(): raise ValueError('An unanswered question cannot contain an answer')
            data['answers'][str(step)] = {k:args.get(k) for k in ('answered','answer','correct')}
        elif name == 'complete_step':
            if item['type'] == 'quiz' and not data['answers'].get(str(step),{}).get('answered'): raise ValueError('Record the learner answer first')
            if step not in data['completed_steps']: data['completed_steps'].append(step)
            data['completed_steps'].sort()
        elif name == 'complete_course':
            if len(data['completed_steps']) != course['step_count']: raise ValueError('Complete every step first')
            data['status'] = 'passed'
        elif name == 'rate_course':
            if data['status'] != 'passed': raise ValueError('Pass the course before rating')
            data['rating'] = args['rating']
        p.data = json.dumps(data)
        next_step = next((s for s in course['steps'] if s['number'] not in data['completed_steps']), None)
        return {'course_id':course['id'], 'progress':data, 'next_step':next_step}
