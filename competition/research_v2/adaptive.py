"""Independent candidate: never decrease power below the original estimate.

Only completed past intervals enter estimation. Initial energy observation,
reserve, uncertainty multipliers, decision triggers and physics are unchanged.
"""
import hashlib
import math
from pathlib import Path
from typing import Literal

from competition.v2.contracts import Record, fingerprint
from competition.v2.runtime import RuntimeConfig, RuntimeRun

VERSION='completed-interval-power-20261113-0.1'


class CandidateConfig(Record):
    experiment_version: Literal['completed-interval-power-20261113-0.1']=VERSION
    base_configuration: RuntimeConfig


def past_power(initial_power,intervals,as_of_s):
    powers=[initial_power]
    for row in intervals:
        if row['partial'] or row['end_s']>as_of_s:continue
        duration=row['end_s']-row['start_s']
        if duration<=0:continue
        observed=3600*row['integrated_wh']/duration
        if not math.isfinite(observed) or observed<0:raise ValueError('invalid_completed_interval_energy')
        powers.append(observed)
    return max(powers)


class CandidateRun(RuntimeRun):
    def __init__(self,parameters:CandidateConfig,library=None,run_id=None):
        self.parameters=parameters
        self.initial_planning_power=None
        super().__init__(parameters.base_configuration,library,run_id)

    def _choose(self,trigger):
        if self.initial_planning_power is None:
            self.initial_planning_power=self.template.model.estimated_power_w
        power=past_power(self.initial_planning_power,self.intervals,self.t_s)
        self.template=self.template.model_copy(update={'model':self.template.model.model_copy(
            update={'estimated_power_w':power})})
        return super()._choose(trigger)

    def export(self):
        archive=super().export()
        config=self.parameters.model_copy(update={'base_configuration':RuntimeConfig.model_validate(archive['configuration'])})
        archive['configuration']=config.model_dump(mode='json')
        archive['configuration_sha256']=fingerprint(config)
        archive['metadata']['archive_kind']='ADAPTIVE_POWER_REQUIRES_RESEARCH_ADAPTER'
        archive['metadata']['experiment_version']=VERSION
        archive['metadata']['initial_planning_power_w']=self.initial_planning_power
        path=Path(__file__).resolve()
        archive['metadata']['source_sha256'][str(path.relative_to(path.parents[2]))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return archive
