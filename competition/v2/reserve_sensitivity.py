"""Explicit, separately versioned reserve experiment using the frozen executor.

This adapter sets the policy before EVERY planning call, including the first
call during construction. Physics, selectors and the production 20% default
remain unchanged. Its archives require this adapter and cannot silently replay
as ordinary RuntimeConfig archives.
"""
from pathlib import Path
import hashlib
from typing import Annotated, Literal

from pydantic import Field, StrictFloat
from .contracts import Record, fingerprint
from .runtime import RuntimeConfig, RuntimeRun

VERSION = 'competition-v2-reserve-sensitivity-0.1'


class SensitivityConfig(Record):
    experiment_version: Literal['competition-v2-reserve-sensitivity-0.1'] = VERSION
    base_configuration: RuntimeConfig
    reserve_fraction: Annotated[StrictFloat, Field(ge=0., le=1.)]


class ReserveRun(RuntimeRun):
    def __init__(self, parameters: SensitivityConfig, library=None, run_id=None):
        self.sensitivity_parameters = parameters
        super().__init__(parameters.base_configuration, library=library, run_id=run_id)
        # Unavailable data can end before any planning call; its declared
        # reserve must still describe the supplied policy, when known.
        self._set_experiment_reserve()

    def _set_experiment_reserve(self):
        if not self.library.available:
            return
        self.reserve_wh = self.library.reference_wh * self.sensitivity_parameters.reserve_fraction
        if hasattr(self, 'template'):
            budget = self.template.budget.model_copy(update={'reserve_wh': self.reserve_wh})
            self.template = self.template.model_copy(update={'budget': budget})

    def _choose(self, trigger):
        self._set_experiment_reserve()
        return super()._choose(trigger)

    def export(self):
        archive = super().export()
        # Preserve manual-event/cancel replay semantics from the base executor.
        config = self.sensitivity_parameters.model_copy(update={
            'base_configuration': RuntimeConfig.model_validate(archive['configuration'])})
        archive['configuration'] = config.model_dump(mode='json')
        archive['configuration_sha256'] = fingerprint(config)
        archive['metadata']['archive_kind'] = 'RESERVE_SENSITIVITY_REQUIRES_EXPERIMENT_ADAPTER'
        archive['metadata']['experiment_version'] = VERSION
        archive['metadata']['reserve_fraction'] = config.reserve_fraction
        path = Path(__file__).resolve()
        archive['metadata']['source_sha256'][str(path.relative_to(path.parents[2]))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return archive
