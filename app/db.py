import os
from sqlalchemy import create_engine, String, Text, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(Text)
class Record(Base):
    __tablename__ = 'records'
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    expires: Mapped[int] = mapped_column(Integer, default=0)
class Progress(Base):
    __tablename__ = 'progress'
    __table_args__ = (UniqueConstraint('user_id', 'course_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    course_id: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(Text, default='{}')
