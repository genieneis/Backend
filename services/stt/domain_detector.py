from dataclasses import dataclass, field

from services.stt.term_dict import TermSet

# 도메인으로 인정할 최소 core_keywords 매칭 수.
# 이 값 미만이면 domain=None 유지 (아직 어느 영역인지 불명확한 상태).
_MIN_SCORE = 2

# 현재 domain을 다른 domain으로 교체하려면 점수 차가 이 값 이상이어야 함.
# 수업 중 지나가는 발화로 domain이 흔들리지 않도록 관성을 줌.
_SWITCH_MARGIN = 2

# 같은 domain 후보가 연속으로 이 횟수만큼 1위여야 실제 전환.
# flush마다 update()가 호출되므로 2 = 연속 2배치(약 10문장) 동안 우세해야 전환.
_CONFIRM_STREAK = 2


@dataclass
class DomainDetector:
    """core_keywords 빈도 기반으로 현재 수업 영역(domain)을 추정·유지하는 클래스.

    LLM을 사용하지 않고 키워드 카운팅만으로 동작하므로 지연 없음.
    """
    term_sets: list[TermSet]
    current_domain: str | None = None
    _candidate: str | None = field(default=None, repr=False)  # 전환 후보 domain
    _streak: int = field(default=0, repr=False)               # 후보 연속 1위 횟수

    def _score_all(self, text: str) -> dict[str, int]:
        """각 domain의 core_keywords가 text에 몇 개 등장하는지 카운트."""
        return {
            ts.domain: sum(1 for kw in ts.core_keywords if kw in text)
            for ts in self.term_sets
        }

    def update(self, text: str) -> str | None:
        """텍스트 윈도우(recent_context + 현재 배치)로 domain을 추정하고 현재 domain을 반환.

        domain 전환은 _MIN_SCORE, _SWITCH_MARGIN, _CONFIRM_STREAK 조건을 모두 충족해야 함.
        조건 미달 시 current_domain을 그대로 유지(None 포함).
        """
        if not self.term_sets:
            return None

        scores = self._score_all(text)
        best = max(scores, key=scores.get)
        best_score = scores[best]
        current_score = scores.get(self.current_domain, 0) if self.current_domain else 0

        # 점수 미달 → domain 미확정 유지
        if best_score < _MIN_SCORE:
            self._candidate = None
            self._streak = 0
            return self.current_domain

        # 현재 domain보다 margin만큼 앞서지 못하면 전환 안 함
        if self.current_domain and best != self.current_domain:
            if best_score - current_score < _SWITCH_MARGIN:
                self._candidate = None
                self._streak = 0
                return self.current_domain

        # 연속성 카운트: 같은 후보가 계속 1위여야 전환
        if best == self._candidate:
            self._streak += 1
        else:
            self._candidate = best
            self._streak = 1

        if self._streak >= _CONFIRM_STREAK:
            self.current_domain = self._candidate
            self._candidate = None
            self._streak = 0

        return self.current_domain
