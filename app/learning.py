import json, uuid
from sqlalchemy import select
from .db import Session, Progress
from .courses import load, catalog

TOOLS = {
 'list_micro_courses': {'description': 'List course IDs, names, descriptions and step counts.', 'properties': {}},
 'search_micro_courses': {'description': 'Search titles, descriptions and course material.', 'properties': {'query': {'type':'string'}}, 'required':['query']},
 'start_or_continue_course': {'description': 'REQUIRED when a learner asks to start or continue a selected course: call this tool before teaching. Immediately deliver the returned next_step according to delivery; do not ask readiness, preferences or personal reflection questions.', 'properties': {'course_id': {'type':'string'}}, 'required':['course_id']},
 'open_step': {'description': 'Retrieve the actual course step before presenting it. Follow delivery: narrate text, let the learner ask in qa, ask only the authored quiz question in quiz. Future steps cannot be opened before prior steps are complete. Opening does not complete anything.', 'properties': {'course_id': {'type':'string'}, 'step': {'type':'integer','minimum':1}}, 'required':['course_id','step']},
 'record_answer': {'description': 'Record whether the learner answered a quiz, their exact answer and optional correctness. Never invent an answer.', 'properties': {'course_id': {'type':'string'}, 'step': {'type':'integer','minimum':1}, 'answered': {'type':'boolean'}, 'answer': {'type':'string','maxLength':10000}, 'correct': {'type':['boolean','null']}}, 'required':['course_id','step','answered','answer']},
 'complete_step': {'description': 'Complete only the current step after its full material has actually been delivered or discussed. Never call before narration or to jump ahead. Quizzes require the learner actual recorded answer. Then follow next_step and delivery.', 'properties': {'course_id': {'type':'string'}, 'step': {'type':'integer','minimum':1}}, 'required':['course_id','step']},
 'complete_course': {'description': 'Mark your course passed after all steps are complete.', 'properties': {'course_id': {'type':'string'}}, 'required':['course_id']},
 'rate_course': {'description': 'Rate your passed course from 1 to 5.', 'properties': {'course_id': {'type':'string'}, 'rating': {'type':'integer','minimum':1,'maximum':5}}, 'required':['course_id','rating']},
 'get_my_learning': {'description': 'List only your started and passed courses, answers, progress and ratings.', 'properties': {}},
}
def delivery_for(item):
    """Give hosts explicit, step-specific behavior without leaking future quizzes."""
    if item is None:
        return {'action': 'finish', 'allow_assistant_questions': False,
                'instruction': 'All steps are complete. Call complete_course if not already passed. Invite a rating only after passing; do not invent another quiz.'}
    common = 'Use only the supplied course material. Do not invent advice, anecdotes, exercises or questions. Never read execution guidance or expected answers aloud. '
    if item['type'] == 'text':
        return {'action': 'narrate', 'allow_assistant_questions': False,
                'instruction': common + 'Start speaking the actual step content now in its original language. Deliver all substantive paragraphs in order, in manageable spoken portions. Do not replace the lesson with a short summary. Do not ask whether the learner is ready, wants an introduction, has personal experience, or wants the next portion. Keep this step incomplete if narration is interrupted. Only after the full narration has been delivered, call complete_step and follow its next_step. Pause if the learner requests it.'}
    if item['type'] == 'qa':
        return {'action': 'invite_learner_questions', 'allow_assistant_questions': False,
                'instruction': common + 'The preceding narration is complete. Briefly invite the learner to ask questions about it, then wait. This is learner-led Q&A, not a quiz or coaching interview. Ground answers only in course_material. When the learner says they have no more questions or asks to continue, complete this step.'}
    return {'action': 'ask_authored_quiz', 'allow_assistant_questions': True,
            'instruction': common + 'Ask only this step content as the authored quiz question, then wait for the actual answer. Do not ask additional reflection questions or reveal expected_answer. Record the actual response before completing the step.'}

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
            if any(previous not in data['completed_steps'] for previous in range(1, step)):
                raise ValueError('Deliver and complete the preceding steps first. Resume the course and narrate the returned text step before Q&A or quiz.')
        if name == 'open_step':
            response = {'step':item, 'progress':data, 'delivery':delivery_for(item)}
            if item['type'] in ('qa', 'quiz'):
                response['course_material'] = [s for s in course['steps'][:step-1] if s['type'] == 'text']
            return response
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
        return {'course_id':course['id'], 'progress':data, 'next_step':next_step, 'delivery':delivery_for(next_step)}
