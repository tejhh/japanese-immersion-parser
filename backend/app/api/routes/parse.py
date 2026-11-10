from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AnalyzerDep, SettingsDep
from app.schemas import ParseRequest, ParseResponse

router = APIRouter(prefix="/parse", tags=["parse"])


@router.post("", response_model=ParseResponse, response_model_exclude_none=True)
def parse_text(payload: ParseRequest, analyzer: AnalyzerDep, settings: SettingsDep) -> ParseResponse:
    """Analyse text on the fly without persisting anything."""
    if len(payload.text) > settings.max_text_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"text exceeds {settings.max_text_chars} characters",
        )
    result = analyzer.analyze(
        payload.text, levels=payload.levels, include_vocabulary=payload.include_vocabulary
    )
    return ParseResponse.from_result(result, include_tokens=payload.include_tokens)
