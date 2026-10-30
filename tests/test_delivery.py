import uuid
import pytest
from app import courses
from app.learning import execute
from app.db import Base, engine

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
    assert 'expected_answer' not in str(opened)
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
    assert 'expected_answer' not in str(opened)
    result=execute(user,'complete_step',{**cid,'step':3})
    assert result['next_step']['type']=='quiz'
    assert result['delivery']['action']=='ask_authored_quiz'
    assert result['delivery']['allow_assistant_questions'] is True
    with pytest.raises(ValueError,match='answer first'):
        execute(user,'complete_step',{**cid,'step':4})
    execute(user,'record_answer',{**cid,'step':4,'answered':True,'answer':'بله','correct':True})
    result=execute(user,'complete_step',{**cid,'step':4})
    assert result['next_step'] is None
    assert result['delivery']['action']=='finish'
