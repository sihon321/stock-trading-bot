"""Bounded saved evidence services. No source mutation or live capabilities."""
from .web_models import OverviewDTO


class ReadOnlyPortfolioRepository:
    pass


class OperatorEvidenceService:
    def __init__(self, settings, *, clock):
        self.settings, self.clock = settings, clock

    def overview(self, scope):
        return OverviewDTO(self.clock())
