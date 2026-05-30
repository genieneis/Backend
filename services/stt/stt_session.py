import time
from dataclasses import dataclass, field

from services.stt.domain_detector import DomainDetector
from services.stt.term_dict import TermSet, load_term_sets

# LLM 보정 요청을 트리거하는 최대 누적 완성 문장 수.
# 이 수에 도달하면 즉시 flush하고 GPT에 보정 요청.
_BATCH_MAX_SENTENCES = 3

# 문장 수가 부족해도 이 시간(초)이 지나면 강제 flush.
# 말이 느린 수업이나 침묵 구간에서 무한정 기다리지 않도록 함.
_BATCH_MAX_SECONDS = 15

# domain 감지용 슬라이딩 윈도우에 포함할 직전 완성 문장 수.
# 너무 적으면 domain 오감지, 너무 많으면 전환 감지가 느려짐.
_RECENT_CONTEXT_SIZE = 2

# domain 미확정 시 전체 priority_terms 중 LLM에 보낼 최대 개수.
# 너무 많으면 GPT 토큰 낭비, 너무 적으면 보정 품질 저하.
_FALLBACK_PRIORITY_LIMIT = 20


@dataclass
class PendingSentence:
    """LLM 보정 대기 중인 완성 문장 (partial 누적 + final delta 결합 결과)."""
    id: int    # 세션 내 순번 (프론트 final_raw id와 대응)
    text: str  # partial 조각들 + final delta를 합친 완성 문장


@dataclass
class STTSession:
    """수업 1회 STT 세션 상태를 관리하는 클래스.

    세션 시작 시 DB에서 과목 term_sets를 로드하고,
    Clova FINAL 결과(완성 문장)를 누적하다가 flush 조건 충족 시
    domain 감지 + LLM 보정에 필요한 데이터를 반환한다.
    """
    school_level: str
    grade_band: str | None   # 초등만 "1~2학년" 등, 중·고등은 None
    subject_name: str

    matched: bool = False                  # DB에서 해당 과목 term_sets를 찾았는지 여부
    term_sets: list[TermSet] = field(default_factory=list)
    detector: DomainDetector = field(default_factory=lambda: DomainDetector(term_sets=[]))

    _recent_context: list[str] = field(default_factory=list, repr=False)  # domain 감지용 직전 문장들
    _pending: list[PendingSentence] = field(default_factory=list, repr=False)  # flush 대기 문장들
    _batch_start: float | None = field(default=None, repr=False)  # 첫 문장 수신 시각 (시간 기반 flush용)
    _next_id: int = field(default=0, repr=False)

    @classmethod
    async def create(
        cls,
        school_level: str,
        grade_band: str | None,
        subject_name: str,
    ) -> "STTSession":
        """DB 조회까지 완료된 세션 생성. WS 연결 직후 1회 호출."""
        session = cls(school_level=school_level, grade_band=grade_band, subject_name=subject_name)
        term_sets = await load_term_sets(school_level, grade_band, subject_name)
        session.term_sets = term_sets
        session.matched = len(term_sets) > 0
        session.detector = DomainDetector(term_sets=term_sets)
        return session

    def add_final(self, text: str) -> int:
        """완성 문장(partial 누적 + final delta)을 pending에 추가. 부여된 sentence id 반환."""
        sid = self._next_id
        self._next_id += 1
        self._pending.append(PendingSentence(id=sid, text=text))
        if self._batch_start is None:
            self._batch_start = time.monotonic()
        return sid

    def should_flush(self) -> bool:
        """flush 조건 충족 여부: 문장 수 도달 OR 시간 초과."""
        if not self._pending:
            return False
        if len(self._pending) >= _BATCH_MAX_SENTENCES:
            return True
        if self._batch_start and time.monotonic() - self._batch_start >= _BATCH_MAX_SECONDS:
            return True
        return False

    def flush(self) -> tuple[list[PendingSentence], str | None, list[str], list[str]]:
        """pending 배치를 꺼내고 (sentences, domain, priority_terms, source_terms) 반환.

        내부적으로 domain 점수 계산과 LLM에 넣을 용어 선택까지 수행.
        - domain 확정: 해당 domain의 priority_terms + source_terms
        - domain 미확정: 전 domain priority_terms 상위 _FALLBACK_PRIORITY_LIMIT개
        - 과목 미매칭: 빈 리스트
        """
        batch = self._pending[:]
        self._pending = []
        self._batch_start = None

        # domain 점수 계산: 직전 문장들(문맥) + 이번 배치를 합친 텍스트 윈도우 사용
        window = " ".join(
            self._recent_context[-_RECENT_CONTEXT_SIZE:]
            + [s.text for s in batch]
        )
        domain = self.detector.update(window) if self.matched else None

        priority_terms: list[str] = []
        source_terms: list[str] = []

        if self.matched:
            if domain:
                # domain 확정: 해당 domain 용어만 LLM에 전달
                ts = next((t for t in self.term_sets if t.domain == domain), None)
                if ts:
                    priority_terms = ts.priority_terms
                    source_terms = ts.source_terms
            else:
                # domain 미확정: 전 domain priority_terms 소량만 전달 (토큰 절약)
                all_priority = [t for ts in self.term_sets for t in ts.priority_terms]
                priority_terms = all_priority[:_FALLBACK_PRIORITY_LIMIT]

        # recent_context 슬라이딩: 이번 배치를 추가하고 오래된 앞부분 제거
        self._recent_context = (
            self._recent_context + [s.text for s in batch]
        )[-_RECENT_CONTEXT_SIZE:]

        return batch, domain, priority_terms, source_terms
