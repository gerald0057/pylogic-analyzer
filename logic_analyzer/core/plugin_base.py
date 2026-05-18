from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    plugin_name: str
    description: str = ""
    data: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


class AnalysisPlugin(ABC):
    @property
    @abstractmethod
    def name(self):
        ...

    @property
    @abstractmethod
    def description(self):
        ...

    def configure_parser(self, parser):
        pass

    @abstractmethod
    def analyze(self, waveform, args) -> AnalysisResult:
        ...
