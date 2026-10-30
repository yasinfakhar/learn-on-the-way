import uuid
import pytest
from app import courses
from app.learning import execute
from app.db import Base, engine

def nested_keys(value):
    if isinstance(value, dict):
        return set(value).union(*(nested_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(v) for v in value))
    return set()

@pytest.fixture
def lesson(tmp_path, monkeypatch):
    # Different from the bundled course: checks behavior for any authored course.
    raw='''---
id: delivery-check
name: آزمون روایت
description: A lesson with narration, learner Q&A, then one authored quiz.
---
## Step 1 [text] شروع
این متن واقعی درس است؛ اول باید آن را شنید.

## Step 2 [text] ادامه
این بخش دوم روایت است.

## Step 3 [qa] سؤال‌های یادگیرنده
اکنون می‌توانید سؤال خودتان را بپرسید.

## Step 4 [quiz] مرور
سؤال آزمون فقط اینجا مطرح می‌شود؟
### Expected answer
بله، پس از روایت و پرسش‌های یادگیرنده.
'''
    (tmp_path/'delivery-check.md').write_text(raw)
    monkeypatch.setattr(courses,'ROOT',tmp_path)
    Base.metadata.create_all(engine)
    return str(uuid.uuid4()), {'course_id':'delivery-check'}


def test_start_narrates_real_content_without_leaking_quiz(lesson):
    user,cid=lesson
    result=execute(user,'start_or_continue_course',cid)
    assert result['next_step']['content']==courses.load(cid['course_id'])['steps'][0]['content']
    assert result['next_step']['type']=='text'
    assert result['delivery']['action']=='narrate'
    assert result['delivery']['allow_assistant_questions'] is False
    assert result['progress']['completed_steps']==[]
    opened=execute(user,'open_step',{**cid,'step':1})
    assert 'course_material' not in opened
    assert 'expected_answer' not in nested_keys(opened)
    assert 'سؤال آزمون فقط اینجا' not in str(opened)
    # Repeated start/open calls must not pretend any narration was delivered.
    assert execute(user,'start_or_continue_course',cid)['next_step']['number']==1


def test_cannot_jump_from_start_into_questions_or_record_a_quiz(lesson):
    user,cid=lesson
    execute(user,'start_or_continue_course',cid)
    for name,args in [
        ('open_step',{'step':3}), ('open_step',{'step':4}),
        ('complete_step',{'step':3}),
        ('record_answer',{'step':4,'answered':True,'answer':'An invented early answer'}),
    ]:
        with pytest.raises(ValueError,match='preceding steps'):
            execute(user,name,{**cid,**args})
    assert execute(user,'get_my_learning',{})[0]['completed_steps']==[]


def test_delivery_transitions_narration_then_learner_qa_then_authored_quiz(lesson):
    user,cid=lesson
    execute(user,'start_or_continue_course',cid)
    result=execute(user,'complete_step',{**cid,'step':1})
    assert result['next_step']['number']==2
    assert result['delivery']['action']=='narrate'
    assert result['delivery']['allow_assistant_questions'] is False
    result=execute(user,'complete_step',{**cid,'step':2})
    assert result['next_step']['type']=='qa'
    assert result['delivery']['action']=='invite_learner_questions'
    opened=execute(user,'open_step',{**cid,'step':3})
    assert len(opened['course_material'])==2
    assert all(step['type']=='text' for step in opened['course_material'])
    assert 'expected_answer' not in nested_keys(opened)
    result=execute(user,'complete_step',{**cid,'step':3})
    assert result['next_step']['type']=='quiz'
    assert result['delivery']['action']=='ask_authored_quiz'
    assert result['delivery']['allow_assistant_questions'] is True
    with pytest.raises(ValueError,match='answer first'):
        execute(user,'complete_step',{**cid,'step':4})
    execute(user,'record_answer',{**cid,'step':4,'answered':True,'answer':'بله','correct':True})
    result=execute(user,'complete_step',{**cid,'step':4})
    assert result['next_step'] is None
    assert result['delivery']['action']=='complete_course'
    assert result['next_action']=={
        'type':'call_tool', 'tool':'complete_course', 'arguments':cid,
        'instruction':'All steps are saved as complete. Call complete_course now. Do not end the conversation or ask for a rating before its success.'
    }


def test_exact_tool_transitions_save_each_step_quiz_and_rating(lesson):
    user,cid=lesson
    started=execute(user,'start_or_continue_course',cid)
    assert started['next_action']['type']=='narrate'
    assert started['next_action']['after_delivery']=={'type':'call_tool','tool':'complete_step','arguments':{**cid,'step':1}}
    assert execute(user,'get_my_learning',{})[0]['completed_steps']==[]
    second=execute(user,'complete_step',started['next_action']['after_delivery']['arguments'])
    assert second['progress']['completed_steps']==[1]
    first_time=second['progress']['step_completed_at']['1']
    repeated=execute(user,'complete_step',{**cid,'step':1})
    assert repeated['progress']['step_completed_at']['1']==first_time
    qa=execute(user,'complete_step',second['next_action']['after_delivery']['arguments'])
    assert qa['next_action']['type']=='invite_learner_questions'
    quiz=execute(user,'complete_step',qa['next_action']['after_learner_done']['arguments'])
    assert quiz['next_action']['question']==quiz['next_step']['content']
    assert quiz['next_action']['wait_for_user'] is True
    assert quiz['next_action']['after_user_answer']['tool']=='record_answer'
    answer=execute(user,'record_answer',{**cid,'step':4,'answered':True,'answer':'بله، بعد از روایت.','correct':True})
    assert answer['next_action']['type']=='call_tool'
    assert answer['next_action']['tool']=='complete_step'
    assert answer['progress']['completed_steps']==[1,2,3]
    assert answer['progress']['answers']['4']['answer']=='بله، بعد از روایت.'
    # A resumed answered quiz should save completion, not ask it again.
    resumed=execute(user,'start_or_continue_course',cid)
    assert resumed['next_action']['tool']=='complete_step'
    final_step=execute(user,'complete_step',answer['next_action']['arguments'])
    assert final_step['workflow_status']['completed_step_count']==4
    assert final_step['workflow_status']['course_passed'] is False
    assert final_step['next_action']['tool']=='complete_course'
    passed=execute(user,'complete_course',final_step['next_action']['arguments'])
    assert passed['progress']['status']=='passed'
    assert passed['progress']['course_completed_at']
    assert passed['next_action']['type']=='request_rating'
    assert passed['next_action']['wait_for_user'] is True
    assert passed['next_action']['after_user_rating']['tool']=='rate_course'
    assert 'rating' not in passed['progress']
    # No rating is fabricated if the learner leaves/declines.
    unrated=execute(user,'start_or_continue_course',cid)
    assert unrated['next_action']['type']=='request_rating'
    assert 'rating' not in execute(user,'get_my_learning',{})[0]
    rated=execute(user,'rate_course',{**cid,'rating':4})
    assert rated['next_action']['type']=='end'
    assert rated['workflow_status']['rating_saved'] is True
    assert rated['progress']['rating_submitted_at']
    assert execute(user,'start_or_continue_course',cid)['next_action']['type']=='end'
    saved=execute(user,'get_my_learning',{})[0]
    assert saved['completed_steps']==[1,2,3,4] and saved['rating']==4 and saved['status']=='passed'


def test_skipped_quiz_does_not_silently_finish_course(lesson):
    user,cid=lesson
    execute(user,'start_or_continue_course',cid)
    for step in (1,2,3): execute(user,'complete_step',{**cid,'step':step})
    skipped=execute(user,'record_answer',{**cid,'step':4,'answered':False,'answer':''})
    assert skipped['next_action']['type']=='ask_authored_quiz'
    assert skipped['progress']['completed_steps']==[1,2,3]
    with pytest.raises(ValueError): execute(user,'complete_course',cid)
    assert 'rating' not in execute(user,'get_my_learning',{})[0]
