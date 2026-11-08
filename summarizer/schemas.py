from typing import Literal
from pydantic import BaseModel, Field


class EmailSummary(BaseModel):
    summary: str = Field(description="ملخص في جملتين على الأكثر")
    action_items: list[str] = Field(description="المطلوب من القارئ عمله")
    deadlines: list[str] = Field(description="المواعيد النهائية المذكورة صراحة فقط")
    urgency_evidence: str = Field(
        description="اقتباس حرفي من الإيميل بيثبت استعجال أو عاقبة تأخير، أو none لو مفيش"
    )
    priority: Literal["high", "medium", "low"]
    priority_reason: str


class Clause(BaseModel):
    topic: str
    detail: str
    reference: str = Field(description="رقم البند/الفقرة في النص، أو 'غير محدد'")


class ContractSummary(BaseModel):
    summary: str = Field(description="ملخص عام في 3-4 جمل")
    parties: list[str]
    term: str = Field(description="مدة العقد وتاريخ البدء والانتهاء")
    payment: str = Field(description="المبالغ وطريقة وموعد الدفع")
    obligations: list[Clause]
    termination: str = Field(description="شروط إنهاء العقد والإخطار")
    ambiguities: list[Clause] = Field(
        description="صياغات غامضة: نسبة أو غرامة من غير تحديد تحسب من إيه، مبلغ من غير أساس، "
        "'مدة معقولة' من غير رقم. اكتب [] لو مفيش"
    )
    risks: list[Clause] = Field(description="بنود تحتاج انتباه (غرامات، تجديد تلقائي، مسؤولية...)")
