from sqlalchemy import Column, Integer, String

try:
    from ..database import Base
except ImportError:  # pragma: no cover
    from database import Base


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)

    fet_id = Column(Integer, unique=True)

    teacher = Column(String)

    subject = Column(String)

    group_name = Column(String)

    duration = Column(Integer)

    day = Column(String)

    start = Column(String)

    room = Column(String)