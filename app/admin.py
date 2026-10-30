"""Operator-only course import and account removal. Run through Docker Compose."""
import argparse, shutil
from pathlib import Path
from sqlalchemy import select, delete
from .courses import load, ROOT
from .db import Session, User, Record, Progress

parser=argparse.ArgumentParser()
sub=parser.add_subparsers(dest='command',required=True)
sub.add_parser('validate-courses')
delete_parser=sub.add_parser('delete-account'); delete_parser.add_argument('email')
args=parser.parse_args()
if args.command=='validate-courses':
    for path in sorted(ROOT.glob('*.md')):
        course=load(path.stem); print(course['id'],course['step_count'])
elif args.command=='delete-account':
    import json
    with Session.begin() as db:
        user=db.scalar(select(User).where(User.email==args.email.strip().casefold()))
        if not user: raise SystemExit('Account not found')
        db.execute(delete(Progress).where(Progress.user_id==user.id))
        for row in db.scalars(select(Record)):
            if json.loads(row.value).get('user_id')==user.id: db.delete(row)
        db.delete(user)
    print('Account, progress, answers and credentials deleted.')
