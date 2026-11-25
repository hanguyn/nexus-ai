from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

READ_ONLY_COMMANDS = {
    "show ip interface brief": "Inspect interface status",
    "show interfaces": "Inspect interface counters and link state",
    "ping <affected-device>": "Check reachability",
    "traceroute <affected-device>": "Inspect the network path",
    "ss -tulnp": "Inspect listening sockets",
}
MANUAL_CHECKS = {
    "Review incident metrics in Prometheus": "Review incident metrics",
    "Compare the recorded dependency paths with inventory": "Review upstream dependencies",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceCitation(StrictModel):
    evidence_id: int = Field(gt=0)
    observed_at: AwareDatetime


class ChecklistStep(StrictModel):
    command_or_action: str
    execution_mode: Literal["read_only", "manual_check"]

    @model_validator(mode="after")
    def validate_action(self):
        allowed = READ_ONLY_COMMANDS if self.execution_mode == "read_only" else MANUAL_CHECKS
        if self.command_or_action not in allowed:
            raise ValueError("Checklist action must match a read-only diagnostic allowlist entry")
        return self

    @property
    def title(self) -> str:
        return (READ_ONLY_COMMANDS | MANUAL_CHECKS)[self.command_or_action]


class IncidentAIExplanationSchema(StrictModel):
    executive_summary: str = Field(min_length=1, max_length=2000)
    technical_explanation: str = Field(min_length=1, max_length=6000)
    impact_assessment: str = Field(min_length=1, max_length=2000)
    checklist: list[ChecklistStep] = Field(min_length=1, max_length=12)
    evidence_citations: list[EvidenceCitation]
    limitations_note: str = Field(min_length=1, max_length=2000)
