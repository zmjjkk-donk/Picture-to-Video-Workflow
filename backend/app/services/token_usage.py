from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy import func, select

from ..models import GenerationJob, TokenUsage


def record_token_usage(session_factory, job_id: str, step_key: str, provider: str, model: str, usage: Mapping[str, object] | None) -> None:
    """Upsert provider-reported usage for one workflow step.

    Missing usage is deliberately ignored. The unique job/step key makes this
    safe when a resumed workflow or polling loop observes the same step again.
    """
    if not usage:
        return
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return
    raw_usage = usage.get("raw_usage_json", "{}")
    if not isinstance(raw_usage, str):
        raw_usage = json.dumps(raw_usage, ensure_ascii=False, sort_keys=True)
    with session_factory() as session:
        row = session.scalar(select(TokenUsage).where(TokenUsage.job_id == job_id, TokenUsage.step_key == step_key))
        values = {
            "provider": provider,
            "model": model,
            "input_tokens": int(input_tokens) if input_tokens is not None else None,
            "output_tokens": int(output_tokens) if output_tokens is not None else None,
            "total_tokens": int(total_tokens) if total_tokens is not None else None,
            "raw_usage_json": raw_usage,
        }
        if row is None:
            session.add(TokenUsage(job_id=job_id, step_key=step_key, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        session.commit()


def aggregate_job_usage(session, job_id: str) -> dict[str, int | str | bool]:
    rows = session.scalars(select(TokenUsage).where(TokenUsage.job_id == job_id)).all()
    if not rows:
        return {"status": "unavailable", "has_data": False, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "step_count": 0}
    return {
        "status": "available",
        "has_data": True,
        "input_tokens": sum(row.input_tokens or 0 for row in rows),
        "output_tokens": sum(row.output_tokens or 0 for row in rows),
        "total_tokens": sum(row.total_tokens or 0 for row in rows),
        "step_count": len(rows),
    }


def aggregate_project_usage(session, project_id: str) -> dict[str, int | str | bool]:
    # Project-level totals represent completed videos. Usage collected during
    # an ultimately failed job remains available on that job for diagnostics,
    # but is not shown as a completed project consumption total.
    rows = session.scalars(select(TokenUsage).join(TokenUsage.job).where(GenerationJob.project_id == project_id, GenerationJob.status == "succeeded")).all()
    if not rows:
        return {"status": "unavailable", "has_data": False, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "step_count": 0}
    return {
        "status": "available",
        "has_data": True,
        "input_tokens": sum(row.input_tokens or 0 for row in rows),
        "output_tokens": sum(row.output_tokens or 0 for row in rows),
        "total_tokens": sum(row.total_tokens or 0 for row in rows),
        "step_count": len(rows),
    }
