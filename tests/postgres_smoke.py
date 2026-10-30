"""Run explicitly against deployed PostgreSQL; cleans up its own disposable user."""
import uuid
from sqlalchemy import delete
from app.db import Session, User, Progress, Record
from app.auth import issue, authenticate
from app.learning import execute
uid=str(uuid.uuid4())
keys=[]
try:
    with Session.begin() as db:
        db.add(User(id=uid,email=uid+'@test.invalid',password='disabled-test-account'))
        credentials=issue(db,uid,'smoke-test','https://learn.sayahub.ir/mcp')
    assert authenticate(credentials['access_token'])==uid
    cid={'course_id':'learning-that-sticks'}
    assert execute(uid,'start_or_continue_course',cid)['next_step']['number']==1
    execute(uid,'complete_step',{**cid,'step':1})
    assert execute(uid,'get_my_learning',{})[0]['completed_steps']==[1]
    print('PostgreSQL token authentication, progress writes and reads passed.')
finally:
    import json
    with Session.begin() as db:
        db.execute(delete(Progress).where(Progress.user_id==uid))
        from sqlalchemy import select
        for row in db.scalars(select(Record)):
            if json.loads(row.value).get('user_id')==uid: db.delete(row)
        user=db.get(User,uid)
        if user: db.delete(user)
