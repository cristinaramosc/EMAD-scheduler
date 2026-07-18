from abc import ABC, abstractmethod

class Constraint(ABC):
    """Base class for all scheduling constraints."""

    @abstractmethod
    def validate(self, schedule):
        """Return a list of conflicts."""
        raise NotImplementedError