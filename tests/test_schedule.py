"""
Tests for :mod:`dateutil.schedule`: a local-wall-clock recurrence adapter
with explicit DST gap/fold handling and UTC half-open range semantics.

Run locally with::

    python -m pytest tests/test_schedule.py -v
"""

from datetime import datetime, timedelta, timezone

import pytest

from dateutil import rrule
from dateutil.schedule import FoldPolicy, GapPolicy, occurrences
from dateutil.tz import gettz

NY = "America/New_York"
UTC = timezone.utc


def _utc(*args):
    return datetime(*args, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Acceptance: spring-forward gap (02:30 does not exist on 2024-03-10 in NY)
# ---------------------------------------------------------------------------


def test_spring_gap_skip():
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 3, 9, 2, 30),
        until=datetime(2024, 3, 11, 2, 30),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 3, 9, 0),
        _utc(2024, 3, 12, 0),
        gap_policy=GapPolicy.SKIP,
    )
    # 03-09 02:30 EST -> 07:30Z ; 03-10 is skipped (gap); 03-11 -> 06:30Z
    assert result == [_utc(2024, 3, 9, 7, 30), _utc(2024, 3, 11, 6, 30)]


def test_spring_gap_forward_lands_on_first_valid_moment():
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 3, 9, 2, 30),
        until=datetime(2024, 3, 11, 2, 30),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 3, 9, 0),
        _utc(2024, 3, 12, 0),
        gap_policy=GapPolicy.FORWARD,
    )
    # The missing 02:30 moves to the first valid instant, 03:00 EDT = 07:00Z.
    assert result == [
        _utc(2024, 3, 9, 7, 30),
        _utc(2024, 3, 10, 7, 0),
        _utc(2024, 3, 11, 6, 30),
    ]


def test_spring_gap_forward_deduplicates_collision():
    # Hourly rule: 02:00 (gap) forwards to 03:00 EDT, which is also the
    # independently generated 03:00 candidate. The shared instant must
    # appear exactly once.
    rule = rrule.rrule(
        rrule.HOURLY,
        dtstart=datetime(2024, 3, 10, 1, 0),
        until=datetime(2024, 3, 10, 4, 0),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 3, 10, 5),
        _utc(2024, 3, 10, 9),
        gap_policy=GapPolicy.FORWARD,
    )
    assert result == [
        _utc(2024, 3, 10, 6, 0),  # 01:00 EST
        _utc(2024, 3, 10, 7, 0),  # 02:00 gap -> 03:00 EDT
        _utc(2024, 3, 10, 8, 0),
    ]  # 04:00 EDT
    assert len(result) == len(set(result))


def test_spring_gap_forward_other_zone_and_tzinfo_object():
    # Europe/Berlin jumps 02:00 -> 03:00 CET on 2024-03-31; 02:30 is
    # missing. Accepting a tzinfo instance must work like a zone name.
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 3, 30, 2, 30),
        until=datetime(2024, 4, 1, 2, 30),
    )
    result = occurrences(
        rule,
        gettz("Europe/Berlin"),
        _utc(2024, 3, 29),
        _utc(2024, 4, 2),
        gap_policy=GapPolicy.FORWARD,
    )
    assert result == [
        _utc(2024, 3, 30, 1, 30),  # 02:30 CET
        _utc(2024, 3, 31, 1, 0),  # gap -> 03:00 CEST
        _utc(2024, 4, 1, 0, 30),  # 02:30 CEST
    ]
    assert result[1].astimezone(gettz("Europe/Berlin")).replace(
        tzinfo=None
    ) == datetime(2024, 3, 31, 3, 0)


# ---------------------------------------------------------------------------
# Acceptance: fall-back fold (01:30 occurs twice on 2024-11-03 in NY)
# ---------------------------------------------------------------------------


def test_fall_fold_both_emits_two_instants_one_hour_apart():
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 11, 2, 1, 30),
        until=datetime(2024, 11, 4, 1, 30),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 2, 0),
        _utc(2024, 11, 5, 0),
        fold_policy=FoldPolicy.BOTH,
    )
    # 11-02 01:30 EDT -> 05:30Z
    # 11-03 01:30 EDT -> 05:30Z and 01:30 EST -> 06:30Z
    # 11-04 01:30 EST -> 06:30Z
    assert result == [
        _utc(2024, 11, 2, 5, 30),
        _utc(2024, 11, 3, 5, 30),
        _utc(2024, 11, 3, 6, 30),
        _utc(2024, 11, 4, 6, 30),
    ]
    dup = [r for r in result if r.date() == _utc(2024, 11, 3).date()]
    assert dup[1] - dup[0] == timedelta(hours=1)


def test_fall_fold_earliest():
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 11, 3, 1, 30),
        until=datetime(2024, 11, 3, 1, 30),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 2, 0),
        _utc(2024, 11, 5, 0),
        fold_policy=FoldPolicy.EARLIEST,
    )
    assert result == [_utc(2024, 11, 3, 5, 30)]


def test_fall_fold_latest():
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 11, 3, 1, 30),
        until=datetime(2024, 11, 3, 1, 30),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 2, 0),
        _utc(2024, 11, 5, 0),
        fold_policy=FoldPolicy.LATEST,
    )
    assert result == [_utc(2024, 11, 3, 6, 30)]


# ---------------------------------------------------------------------------
# UTC half-open range filtering (the second leg must not be lost)
# ---------------------------------------------------------------------------


def test_range_is_half_open_on_utc_timeline():
    # Ambiguous 01:30 gives 05:30Z (earlier) and 06:30Z (later).
    rule = rrule.rrule(
        rrule.DAILY,
        dtstart=datetime(2024, 11, 3, 1, 30),
        until=datetime(2024, 11, 3, 1, 30),
    )
    # Start exactly at the earlier leg (included); end exactly at the later
    # leg (excluded): earlier kept, later excluded.
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 3, 5, 30),
        _utc(2024, 11, 3, 6, 30),
        fold_policy=FoldPolicy.BOTH,
    )
    assert result == [_utc(2024, 11, 3, 5, 30)]

    # A window expressed in UTC that contains only the later leg still keeps
    # it -- this would be silently dropped by a wall-clock comparison.
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 3, 6, 0),
        _utc(2024, 11, 3, 7, 0),
        fold_policy=FoldPolicy.BOTH,
    )
    assert result == [_utc(2024, 11, 3, 6, 30)]


def test_result_sorted_unique_and_utc_aware():
    rule = rrule.rrule(
        rrule.MINUTELY,
        dtstart=datetime(2024, 3, 10, 1, 55),
        until=datetime(2024, 11, 3, 2, 5),
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 3, 9, 0),
        _utc(2024, 11, 5, 0),
        gap_policy=GapPolicy.FORWARD,
        fold_policy=FoldPolicy.BOTH,
    )
    assert result == sorted(result)
    assert len(result) == len(set(result))
    assert all(dt.tzinfo is not None for dt in result)


# ---------------------------------------------------------------------------
# COUNT semantics: counts local candidates, not UTC outputs
# ---------------------------------------------------------------------------


def test_count_counts_local_candidates_fold_both_can_grow_output():
    # COUNT=3 selects the three local days 11-02..11-04; the ambiguous
    # middle one emits two UTC instants, so output length is 4.
    rule = rrule.rrule(
        rrule.DAILY, dtstart=datetime(2024, 11, 2, 1, 30), count=3
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 1, 0),
        _utc(2024, 11, 6, 0),
        fold_policy=FoldPolicy.BOTH,
    )
    assert len(result) == 4
    local = rule.between(datetime(2024, 11, 1), datetime(2024, 11, 6), inc=True)
    assert len(local) == 3


def test_count_counts_local_candidates_gap_skip_can_shrink_output():
    # COUNT=3 local days 03-09..03-11; the 03-10 gap is skipped, leaving 2.
    rule = rrule.rrule(
        rrule.DAILY, dtstart=datetime(2024, 3, 9, 2, 30), count=3
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 3, 8, 0),
        _utc(2024, 3, 13, 0),
        gap_policy=GapPolicy.SKIP,
    )
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Input validation and policy strings
# ---------------------------------------------------------------------------


def test_naive_range_rejected():
    rule = rrule.rrule(
        rrule.DAILY, dtstart=datetime(2024, 3, 9, 2, 30), count=1
    )
    with pytest.raises(ValueError):
        occurrences(rule, NY, datetime(2024, 3, 9), _utc(2024, 3, 12))


def test_aware_rule_rejected():
    rule = rrule.rrule(
        rrule.DAILY, dtstart=datetime(2024, 3, 9, 2, 30, tzinfo=UTC), count=1
    )
    with pytest.raises(ValueError):
        occurrences(rule, NY, _utc(2024, 3, 9), _utc(2024, 3, 12))


def test_policy_value_strings_accepted():
    rule = rrule.rrule(
        rrule.DAILY, dtstart=datetime(2024, 11, 3, 1, 30), count=1
    )
    result = occurrences(
        rule,
        NY,
        _utc(2024, 11, 2, 0),
        _utc(2024, 11, 5, 0),
        fold_policy="earliest",
    )
    assert result == [_utc(2024, 11, 3, 5, 30)]


def test_rruleset_supported():
    rs = rrule.rruleset()
    rs.rrule(
        rrule.rrule(rrule.DAILY, dtstart=datetime(2024, 11, 3, 1, 30), count=1)
    )
    result = occurrences(
        rs,
        NY,
        _utc(2024, 11, 2, 0),
        _utc(2024, 11, 5, 0),
        fold_policy=FoldPolicy.BOTH,
    )
    assert result == [_utc(2024, 11, 3, 5, 30), _utc(2024, 11, 3, 6, 30)]
