from sqlalchemy import Column, Integer, String

try:
    from ..database import Base
except ImportError:  # pragma: no cover
    from database import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    def __repr__(self):
        return f"<Teacher(name='{self.name}')>"