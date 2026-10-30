"""One runtime workflow contract shared by all MCP clients and tool responses."""
HOST_INSTRUCTIONS = '''You are playing a Learn on the Way course. For every tool result follow next_action, not a workflow invented from the course title. Do not stop after narration: persist and continue the authored sequence.
1. On start/continue call start_or_continue_course. A text step means narrate its actual content in order; no invented coaching questions or advice. After its full narration has actually been delivered, call the exact after_delivery tool (complete_step). Never mark interrupted or undelivered narration complete.
2. complete_step saves progress and returns the next authored step. Follow it immediately. For qa invite the learner's questions, answer from supplied course material, and call after_learner_done (complete_step) when they say no questions or continue.
3. For quiz ask the authored question and WAIT for the actual answer. Call record_answer with answered=true and their exact answer; if skipped use answered=false and an empty answer. A question is not complete just because it was asked. Follow the record_answer response: an answered quiz requires complete_step next, not asking the quiz again.
4. After the last step, next_action requires complete_course. Call it; do not claim the course is passed until that call succeeds.
5. complete_course returns next_action=request_rating. Ask its 1-to-5 rating question and WAIT. Call rate_course only with the learner's actual integer rating. If they decline, do not fabricate a rating or ask again in that conversation. A saved rating ends the session.
These are required tool transitions after the relevant speech or user event, not optional suggestions. Do not ask readiness or personal reflection questions in text steps. Speak in the course language. Do not read execution guidance or expected answers. Pause on request or when driving needs attention. Only the host can observe actual speech delivery; never infer it from a successful read tool.'''


def tool_call(name, arguments):
    return {'type': 'call_tool', 'tool': name, 'arguments': arguments}


def workflow(course, data, item):
    cid = course['id']
    if item is None:
        if data['status'] != 'passed':
            action = {**tool_call('complete_course', {'course_id': cid}),
                      'instruction': 'All steps are saved as complete. Call complete_course now. Do not end the conversation or ask for a rating before its success.'}
            return {'action': 'complete_course', 'allow_assistant_questions': False, 'instruction': action['instruction']}, action
        if 'rating' not in data:
            persian = any('\u0600' <= c <= '\u06ff' for c in course['name'])
            prompt = 'این دوره را چطور ارزیابی می‌کنید؟ از ۱ تا ۵ چه امتیازی می‌دهید؟' if persian else 'How would you rate this course from 1 to 5?'
            action = {'type': 'request_rating', 'prompt': prompt, 'wait_for_user': True,
                      'after_user_rating': {'tool': 'rate_course', 'arguments': {'course_id': cid}, 'rating_from': 'The learner actual integer rating, 1 through 5; never invent it.'},
                      'instruction': 'The course is now passed. Ask prompt now, then wait. Save the learner rating with rate_course. If they decline, end without a rating.'}
            return {'action': 'request_rating', 'allow_assistant_questions': True, 'instruction': action['instruction']}, action
        action = {'type': 'end', 'instruction': 'The course is passed and the rating is saved. Acknowledge briefly; do not repeat the quiz or request another rating.'}
        return {'action': 'done', 'allow_assistant_questions': False, 'instruction': action['instruction']}, action

    complete = tool_call('complete_step', {'course_id': cid, 'step': item['number']})
    if item['type'] == 'quiz' and data['answers'].get(str(item['number']), {}).get('answered'):
        action = {**complete, 'instruction': 'The learner actual answer is already saved. Call complete_step now; do not ask the same question again.'}
        return {'action': 'save_step_completion', 'allow_assistant_questions': False, 'instruction': action['instruction']}, action
    common = 'Use only the supplied course material. Never invent claims, exercises or extra questions. Execution guidance and expected_answer are instructor-only. '
    if item['type'] == 'text':
        action = {'type': 'narrate', 'content_field': 'next_step.content (or step.content for open_step)',
                  'after_delivery': complete, 'wait_for_user': False,
                  'instruction': common + 'Narrate all substantive paragraphs now in the course language. Do not substitute a brief summary or ask readiness/reflection questions. After the full narration, you MUST call after_delivery to persist this step and obtain the next action. Do not finish the session after just reading. If interrupted, keep this step incomplete.'}
        return {'action': 'narrate', 'allow_assistant_questions': False, 'instruction': action['instruction']}, action
    if item['type'] == 'qa':
        action = {'type': 'invite_learner_questions', 'wait_for_user': True,
                  'after_learner_done': complete,
                  'instruction': common + 'Briefly invite questions and wait. Answer from preceding narrative material; do not quiz or coach. When the learner has no questions or asks to continue, you MUST call after_learner_done to save this step and obtain the quiz or next step. Do not end the course here.'}
        return {'action': 'invite_learner_questions', 'allow_assistant_questions': False, 'instruction': action['instruction']}, action
    action = {'type': 'ask_authored_quiz', 'question': item['content'], 'wait_for_user': True,
              'after_user_answer': {'tool': 'record_answer', 'arguments': {'course_id': cid, 'step': item['number']}, 'answered_from': 'true only for an actual learner answer', 'answer_from': 'exact learner response; empty string if skipped', 'correct_from': 'assess only using expected_answer'},
              'instruction': common + 'Ask question now and wait for the learner. You MUST call record_answer with their actual response before completing this step. Follow that tool response to call complete_step. Asking the question alone does not complete it. Do not disclose expected_answer.'}
    return {'action': 'ask_authored_quiz', 'allow_assistant_questions': True, 'instruction': action['instruction']}, action


def course_response(course, data, item, step_key='next_step'):
    delivery, action = workflow(course, data, item)
    result = {'workflow_version': '2026-10-30.2', 'next_action': action, 'course_id': course['id'], 'progress': data,
              step_key: item, 'delivery': delivery,
              'workflow_status': {'completed_step_count': len(data['completed_steps']), 'total_steps': course['step_count'],
                                  'course_passed': data['status'] == 'passed', 'rating_saved': 'rating' in data}}
    if item and item['type'] in ('qa','quiz'):
        result['course_material'] = [s for s in course['steps'][:item['number']-1] if s['type'] == 'text']
    return result
