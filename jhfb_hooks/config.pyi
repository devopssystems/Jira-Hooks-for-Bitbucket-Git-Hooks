from pathlib import Path
from typing import FrozenSet

from .output_level import OutputComponent, OutputConfig
from .severity_filter import SeverityFilter

class CommitCheckConfig:
    url: str
    secret: str
    output_levels: FrozenSet[OutputComponent]
    output_config: OutputConfig
    severity_filter: SeverityFilter
    locale: str
    show_conditions: bool
    rich_output: bool
    def __init__(
        self,
        *,
        url: str,
        secret: str,
        output_levels: FrozenSet[OutputComponent] = ...,
        output_config: OutputConfig = ...,
        severity_filter: SeverityFilter = ...,
        locale: str = ...,
        show_conditions: bool = ...,
        rich_output: bool = ...,
    ) -> None: ...

class ConfigNotFoundError(FileNotFoundError): ...
class ConfigMissingKeyError(KeyError): ...
class ConfigInvalidValueError(ValueError): ...

def load_config(env_file: Path) -> CommitCheckConfig: ...
