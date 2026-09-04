from datetime import datetime, timezone
from typing import Generic, TypeVar, Optional, List, Any
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")

class ResponseMeta(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = None

class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None

class ErrorInfo(BaseModel):
    code: str
    message: str
    details: List[ErrorDetail] = Field(default_factory=list)

class ResponseEnvelope(BaseModel, Generic[DataT]):
    success: bool = True
    data: Optional[DataT] = None
    error: Optional[ErrorInfo] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    @classmethod
    def ok(cls, data: DataT, request_id: Optional[str] = None) -> "ResponseEnvelope[DataT]":
        return cls(
            success=True,
            data=data,
            error=None,
            meta=ResponseMeta(request_id=request_id)
        )

    @classmethod
    def fail(cls, code: str, message: str, details: Optional[List[ErrorDetail]] = None, request_id: Optional[str] = None) -> "ResponseEnvelope[None]":
        return cls(
            success=False,
            data=None,
            error=ErrorInfo(code=code, message=message, details=details or []),
            meta=ResponseMeta(request_id=request_id)
        )
