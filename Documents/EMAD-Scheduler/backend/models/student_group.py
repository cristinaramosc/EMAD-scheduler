from sqlalchemy import Column, Integer, String

try:
    from ..database import Base
except ImportError:  # pragma: no cover
    from database import Base