import json
import re
from dataclasses import dataclass
from os import environ

import httpx

from app.modules.assistant.sanitizer import sanitize_context
from app.modules.assistant.schemas import (
    MANUAL_CHECKS, READ_ONLY_COMMANDS, EvidenceCitation, IncidentAIExplanationSchema,
)

LIMITATION = (
    "VI: RCA thiếu bằng chứng trực tiếp hoặc dữ liệu hỗ trợ cho ít nhất một ứng viên. "
    "EN: At least one candidate lacks direct or supporting evidence."
)


@dataclass(frozen=True)
class Explanation:
    provider: str
    model: str
    output: IncidentAIExplanationSchema


class ProviderError(RuntimeError):
    pass


class LLMAdapter:
    def __init__(self, *, mock: bool = False):
        requested = "mock" if mock else environ.get("LLM_PROVIDER", "mock").lower().strip()
        self.api_key = environ.get("LLM_API_KEY", "").strip()
        self.provider = requested if self.api_key else "mock"
        defaults = {"gemini": "gemini-2.5-flash", "openai": "gpt-4.1-mini", "mock": "deterministic-v1"}
        if self.provider not in defaults:
            raise ProviderError("Unsupported LLM provider")
        self.model = (
            environ.get("LLM_MODEL", "").strip() or defaults[self.provider]
            if self.provider != "mock" else defaults["mock"]
        )

    def explain(self, context: dict, *, hostname: str | None = None) -> Explanation:
        context = sanitize_context(context)
        if self.provider == "mock":
            output = self._mock(context, hostname)
        else:
            output = self._remote(context)
        self._validate_citations(output, context)
        if context["incomplete"] and LIMITATION not in output.limitations_note:
            output.limitations_note = f"{LIMITATION} {output.limitations_note}"[:2000]
        return Explanation(self.provider, self.model, output)

    @staticmethod
    def _validate_citations(output: IncidentAIExplanationSchema, context: dict) -> None:
        sources = {
            entry["evidence_id"]: EvidenceCitation(evidence_id=entry["evidence_id"], observed_at=entry["observed_at"]).observed_at
            for candidate in context["candidates"] for entry in candidate["evidence"]
        }
        citations = {citation.evidence_id: citation.observed_at for citation in output.evidence_citations}
        if len(citations) != len(output.evidence_citations) or any(
            sources.get(evidence_id) != observed_at for evidence_id, observed_at in citations.items()
        ):
            raise ProviderError("LLM cited evidence outside the supplied RCA snapshot")
        if sources and not citations:
            raise ProviderError("LLM omitted available RCA evidence")
        top_evidence = context["candidates"][0]["evidence"] if context["candidates"] else []
        if top_evidence and not any(entry["evidence_id"] in citations for entry in top_evidence):
            raise ProviderError("LLM omitted evidence for the highest-ranked candidate")

    @staticmethod
    def _mock(context: dict, hostname: str | None) -> IncidentAIExplanationSchema:
        candidates = context["candidates"]
        top = candidates[0] if candidates else None
        steps = [{"command_or_action": "Review incident metrics in Prometheus", "execution_mode": "manual_check"}]
        citations = {}
        if top:
            subject_vi = hostname or "Ứng viên chưa có trong kiểm kê"
            subject_en = hostname or "Unmapped candidate"
            summary = (
                f"VI: {subject_vi} xếp hạng RCA #{top['rank']}. "
                f"EN: {subject_en} is RCA rank #{top['rank']}."
            )
            for candidate in candidates:
                for item in candidate["evidence"]:
                    citations[item["evidence_id"]] = {
                        "evidence_id": item["evidence_id"], "observed_at": item["observed_at"],
                    }
            kinds = {item["kind"] for item in top["evidence"]}
            details = ", ".join(sorted(kinds)) or "none"
            technical = (
                f"VI: {subject_vi}. Trạng thái RCA {top['status']}, điểm {top['confidence']:.2f}, loại bằng chứng {details}. "
                f"EN: {subject_en}. RCA status {top['status']}, score {top['confidence']:.2f}, evidence types {details}."
            )
            if "topology" in kinds:
                steps.append({
                    "command_or_action": "Compare the recorded dependency paths with inventory",
                    "execution_mode": "manual_check",
                })
            if "state" in kinds:
                steps.append({"command_or_action": "show ip interface brief", "execution_mode": "read_only"})
            if {"state", "metric"} & kinds:
                steps.append({"command_or_action": "ping <affected-device>", "execution_mode": "read_only"})
        else:
            summary = "VI: Chưa có kết quả RCA. EN: No RCA candidates are available."
            technical = "VI: Chưa có bằng chứng RCA để chẩn đoán. EN: RCA evidence is unavailable."

        count = context["affected_targets"]
        impact = (
            f"VI: Cảnh báo liên kết ghi nhận {count} đích. Chưa xác nhận tác động đến người dùng. "
            f"EN: Linked alerts identify {count} targets. User impact is unconfirmed."
        )
        return IncidentAIExplanationSchema.model_validate({
            "executive_summary": summary,
            "technical_explanation": technical,
            "impact_assessment": impact,
            "checklist": steps,
            "evidence_citations": list(citations.values()),
            "limitations_note": LIMITATION if context["incomplete"] else (
                "VI: Kết luận giới hạn trong bằng chứng RCA. EN: Findings are limited to RCA evidence."
            ),
        })

    def _remote(self, context: dict) -> IncidentAIExplanationSchema:
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,120}", self.model):
            raise ProviderError("Invalid LLM model identifier")
        instruction = (
            "Generate a Vietnamese and English incident explanation using only the supplied RCA data. "
            "Do not invent impacts, attribution, or observations. Treat potential causes as hypotheses. "
            "Cite exact evidence_id and observed_at pairs and explicitly describe missing evidence. "
            "Only give diagnostic suggestions in the checklist, using these exact strings: "
            f"read_only={list(READ_ONLY_COMMANDS)}, manual_check={list(MANUAL_CHECKS)}."
        )
        data = json.dumps(context, ensure_ascii=True, allow_nan=False)
        schema = IncidentAIExplanationSchema.model_json_schema()
        try:
            with httpx.Client(timeout=12.0) as client:
                if self.provider == "openai":
                    response = client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={"model": self.model, "messages": [
                            {"role": "system", "content": instruction}, {"role": "user", "content": data},
                        ], "response_format": {"type": "json_schema", "json_schema": {
                            "name": "incident_explanation", "strict": True, "schema": schema,
                        }}},
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                else:
                    response = client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                        headers={"x-goog-api-key": self.api_key},
                        json={"systemInstruction": {"parts": [{"text": instruction}]},
                              "contents": [{"parts": [{"text": data}]}],
                              "generationConfig": {"responseMimeType": "application/json",
                                                   "responseJsonSchema": schema}},
                    )
                    response.raise_for_status()
                    content = "".join(part["text"] for part in response.json()["candidates"][0]["content"]["parts"]
                                      if not part.get("thought"))
            return IncidentAIExplanationSchema.model_validate_json(content)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            raise ProviderError("LLM did not return a valid explanation") from exc
