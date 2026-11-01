"""
試合日程からフェーズ（実行すべき処理）を算出する純粋関数群。

KO（キックオフ）時刻を基準にした相対時間でフェーズを決定し、
「予定時刻を過ぎていて未処理」なら実行対象とする（冪等なポーリング型）。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

JST = timezone(timedelta(hours=9))

PREVIEW_DRAFT = "preview_draft"
PREVIEW_FINAL = "preview_final"
STAGE1 = "stage1"
STAGE2 = "stage2"

# フェーズ名 -> KO からのオフセット（実行開始可能になる時刻）
PHASE_OFFSETS: Dict[str, timedelta] = {
    PREVIEW_DRAFT: timedelta(hours=-72),
    PREVIEW_FINAL: timedelta(hours=-24),
    STAGE1: timedelta(hours=3),
    STAGE2: timedelta(hours=36),
}

# 実行順序（早いフェーズから）
PHASE_ORDER: List[str] = [PREVIEW_DRAFT, PREVIEW_FINAL, STAGE1, STAGE2]

# 試合後は preview 系をスキップする
PREVIEW_PHASES = (PREVIEW_DRAFT, PREVIEW_FINAL)


def parse_kickoff(date_str: str, time_str: str) -> Optional[datetime]:
    """'YYYY-MM-DD' と 'HH:MM' から JST の KO 日時を返す。不正なら None。"""
    try:
        naive = datetime.strptime(f"{date_str} {time_str.strip()}", "%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return None
    return naive.replace(tzinfo=JST)


def compute_phase_schedule(kickoff: datetime) -> Dict[str, datetime]:
    """KO 日時から各フェーズの実行開始可能時刻を返す。"""
    return {phase: kickoff + offset for phase, offset in PHASE_OFFSETS.items()}


def pending_phases(
    kickoff: datetime,
    now: datetime,
    done: Iterable[str],
) -> List[str]:
    """
    実行すべき未処理フェーズを実行順に返す。

    - 予定時刻 <= now かつ done に含まれないフェーズが対象。
    - KO 後は preview 系をスキップする。
    - stage2 が未処理でも stage1 が未処理なら両方返す（取りこぼし救済）。
    """
    done_set: Set[str] = set(done)
    schedule = compute_phase_schedule(kickoff)
    after_kickoff = now >= kickoff
    result: List[str] = []
    for phase in PHASE_ORDER:
        if phase in done_set:
            continue
        if after_kickoff and phase in PREVIEW_PHASES:
            continue
        if schedule[phase] <= now:
            result.append(phase)
    return result


def done_phases_from_stage(source_updated_stage: Optional[int]) -> Set[str]:
    """DB の source_updated_stage（None/0/1/2）から完了済み stage を返す。"""
    stage = source_updated_stage or 0
    done: Set[str] = set()
    if stage >= 1:
        done.add(STAGE1)
    if stage >= 2:
        done.add(STAGE2)
    return done


def plan_matches(
    matches: List[Dict[str, Any]],
    now: datetime,
    done_lookup: Dict[str, Set[str]],
) -> List[Dict[str, Any]]:
    """
    試合リスト（schedule_crawler 形式）から、実行すべき試合・フェーズの一覧を作る。

    done_lookup: match_id -> 完了済みフェーズ集合。
    """
    plan: List[Dict[str, Any]] = []
    for match in matches:
        kickoff = parse_kickoff(match.get("date", ""), match.get("time", ""))
        if kickoff is None:
            continue
        match_id = match.get("match_id", "")
        phases = pending_phases(kickoff, now, done_lookup.get(match_id, set()))
        if not phases:
            continue
        plan.append(
            {
                "match_id": match_id,
                "matchweek": match.get("matchweek"),
                "kickoff": kickoff.isoformat(),
                "phases": phases,
                "pending_phases": phases,
                "home": match.get("home"),
                "away": match.get("away"),
            },
        )
    return plan

