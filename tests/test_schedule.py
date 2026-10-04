"""
Tests for :mod:`dateutil.schedule` -- the rrule-based schedule adapter.

The scenarios use America/New_York: spring forward (a wall-clock gap) and
fall back (a wall-clock repeat) on 2024-03-10 and 2024-11-03.  If the
system zoneinfo database is unavailable (e.g. on Windows), an equivalent
POSIX rule with the same transition dates is used.
"""

from datetime import datetime, timedelta

import pytest

from dateutil import tz
from dateutil.rrule import DAILY, HOURLY, rrule
from dateutil.schedule import BOTH, EARLIER, LATER, SHIFT, SKIP, Schedule

UTC = tz.UTC

# 02:30 on 2024-03-10 in New York: the wall clock jumps from 02:00 to
# 03:00, so 02:30 does not exist.
SPRING = datetime(2024, 3, 10, 2, 30)

# 01:30 on 2024-11-03 in New York: the wall clock goes from EDT back to
# EST, so 01:30 occurs twice.
FALL = datetime(2024, 11, 3, 1, 30)


@pytest.fixture
def nyc():
    import warnings

    with warnings.catch_warnings():
        # The zoneinfo tarball may be absent (e.g. a source checkout
        # without zic); the IANA lookup warns and returns None.
        warnings.simplefilter("ignore")
        z = tz.gettz("America/New_York")
    if z is None:
        # Equivalent POSIX TZ string (US transition rules since 2007:
        # second Sunday in March, first Sunday in November).
        z = tz.tzstr("EST5EDT4,M3.2.0/2,M11.1.0/2")
    return z


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ----------------------------------------------------------------------
# Nonexistent (imaginary) wall-clock times: spring forward
# ----------------------------------------------------------------------
def test_spring_skip_drops_the_imaginary_candidate(nyc):
    rule = rrule(DAILY, dtstart=SPRING, count=1)
    sched = Schedule(rule, nyc, nonexistent=SKIP)

    out = sched.between(utc(2024, 3, 10), utc(2024, 3, 11))

    assert out == []


def test_spring_shift_moves_to_first_valid_instant(nyc):
    rule = rrule(DAILY, dtstart=SPRING, count=1)
    sched = Schedule(rule, nyc, nonexistent=SHIFT)

    out = sched.between(utc(2024, 3, 10), utc(2024, 3, 11))

    # 02:30 EST does not exist; shifted forward it becomes 03:30 EDT,
    # i.e. 07:30 UTC.
    assert out == [utc(2024, 3, 10, 7, 30)]
    assert out[0].astimezone(nyc).replace(tzinfo=None) == datetime(
        2024, 3, 10, 3, 30
    )


def test_skip_and_shift_agree_on_a_normal_day(nyc):
    rule = rrule(DAILY, dtstart=datetime(2024, 7, 4, 12, 0), count=1)
    skipped = Schedule(rule, nyc, nonexistent=SKIP)
    shifted = Schedule(rule, nyc, nonexistent=SHIFT)

    rng = (utc(2024, 7, 4), utc(2024, 7, 5))
    assert (
        skipped.between(*rng)
        == shifted.between(*rng)
        == [utc(2024, 7, 4, 16, 0)]
    )  # EDT is UTC-4


# ----------------------------------------------------------------------
# Ambiguous (repeated) wall-clock times: fall back
# ----------------------------------------------------------------------
def test_fall_earlier_offset(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=EARLIER)

    out = sched.between(utc(2024, 11, 3), utc(2024, 11, 4))

    assert out == [utc(2024, 11, 3, 5, 30)]  # EDT (UTC-4)


def test_fall_later_offset(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=LATER)

    out = sched.between(utc(2024, 11, 3), utc(2024, 11, 4))

    assert out == [utc(2024, 11, 3, 6, 30)]  # EST (UTC-5)


def test_fall_both_offsets_are_one_hour_apart(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=BOTH)

    out = sched.between(utc(2024, 11, 3), utc(2024, 11, 4))

    assert out == [utc(2024, 11, 3, 5, 30), utc(2024, 11, 3, 6, 30)]
    assert out[1] - out[0] == timedelta(hours=1)


# ----------------------------------------------------------------------
# The selection range is a UTC half-open interval [start, end)
# ----------------------------------------------------------------------
def test_range_is_half_open_on_the_utc_instants(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=BOTH)

    # Start inclusive: the 05:30 instant is exactly at the start.
    assert sched.between(utc(2024, 11, 3, 5, 30), utc(2024, 11, 3, 6, 30)) == [
        utc(2024, 11, 3, 5, 30)
    ]
    # End exclusive: the 06:30 instant is exactly at the end.
    assert sched.between(utc(2024, 11, 3, 5, 31),
                         utc(2024, 11, 3, 6, 30)) == []
    # Widening the end admits the second occurrence.
    assert sched.between(utc(2024, 11, 3, 5, 30), utc(2024, 11, 3, 6, 31)) == [
        utc(2024, 11, 3, 5, 30),
        utc(2024, 11, 3, 6, 30),
    ]


def test_utc_filtering_keeps_the_second_occurrence(nyc):
    # A wall-clock range cannot express this: [05:00, 07:00) UTC maps to
    # a single wall-clock candidate (01:30), but that candidate has two
    # UTC instants, both of which must survive the UTC filter.
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=BOTH)

    out = sched.between(utc(2024, 11, 3, 5, 0), utc(2024, 11, 3, 7, 0))

    assert out == [utc(2024, 11, 3, 5, 30), utc(2024, 11, 3, 6, 30)]


def test_naive_range_is_treated_as_utc(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=BOTH)

    out = sched.between(
        datetime(2024, 11, 3, 5, 0), datetime(2024, 11, 3, 7, 0)
    )

    assert out == [utc(2024, 11, 3, 5, 30), utc(2024, 11, 3, 6, 30)]


def test_aware_range_in_another_zone_is_converted_to_utc(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)
    sched = Schedule(rule, nyc, ambiguous=BOTH)

    # UTC+2: 07:00..09:00 local == 05:00..07:00 UTC.
    plus2 = tz.tzoffset(None, 2 * 3600)
    out = sched.between(
        datetime(2024, 11, 3, 7, 0, tzinfo=plus2),
        datetime(2024, 11, 3, 9, 0, tzinfo=plus2),
    )

    assert out == [utc(2024, 11, 3, 5, 30), utc(2024, 11, 3, 6, 30)]


# ----------------------------------------------------------------------
# De-duplication: a shifted imaginary time may collide with a candidate
# ----------------------------------------------------------------------
def test_shift_that_hits_another_candidate_is_deduped(nyc):
    # Hourly on the spring-forward day: the 02:30 candidate is shifted to
    # 03:30 wall clock, which is the same UTC instant as the 03:30
    # candidate.
    rule = rrule(HOURLY, dtstart=datetime(2024, 3, 10, 0, 30), count=5)
    sched = Schedule(rule, nyc, nonexistent=SHIFT)

    out = sched.between(utc(2024, 3, 10), utc(2024, 3, 11))

    assert out == [
        utc(2024, 3, 10, 5, 30),
        utc(2024, 3, 10, 6, 30),
        utc(2024, 3, 10, 7, 30),
        utc(2024, 3, 10, 8, 30),
    ]
    assert len(out) == len(set(out))


def test_output_is_always_ordered_and_unique(nyc):
    rule = rrule(HOURLY, dtstart=datetime(2024, 3, 10, 0, 30), count=5)
    sched = Schedule(rule, nyc, nonexistent=SHIFT)

    out = sched.between(utc(2024, 3, 10), utc(2024, 3, 11))

    assert out == sorted(out)
    assert len(out) == len(set(out))


# ----------------------------------------------------------------------
# COUNT counts rule candidates, not output instants
# ----------------------------------------------------------------------
def test_count_counts_rule_candidates_not_outputs(nyc):
    # Four rule candidates, but the 01:30 candidate doubles under BOTH,
    # so COUNT=4 produces 5 output instants.
    rule = rrule(HOURLY, dtstart=datetime(2024, 11, 3, 0, 30), count=4)
    assert rule.count() == 4

    sched = Schedule(rule, nyc, ambiguous=BOTH)
    out = sched.between(utc(2024, 11, 3), utc(2024, 11, 4))

    assert len(out) == 5
    assert out == [
        utc(2024, 11, 3, 4, 30),
        utc(2024, 11, 3, 5, 30),
        utc(2024, 11, 3, 6, 30),
        utc(2024, 11, 3, 7, 30),
        utc(2024, 11, 3, 8, 30),
    ]


def test_skip_reduces_output_count_below_rule_count(nyc):
    # Two rule candidates; the spring 02:30 candidate is skipped, so
    # COUNT=2 produces 1 output instant.
    rule = rrule(DAILY, dtstart=datetime(2024, 3, 9, 2, 30), count=2)
    assert rule.count() == 2

    sched = Schedule(rule, nyc, nonexistent=SKIP)
    out = sched.between(utc(2024, 3, 9), utc(2024, 3, 11))

    assert len(out) == 1
    assert out == [utc(2024, 3, 9, 7, 30)]


# ----------------------------------------------------------------------
# Iteration and validation
# ----------------------------------------------------------------------
def test_iter_matches_between(nyc):
    rule = rrule(HOURLY, dtstart=datetime(2024, 11, 3, 0, 30), count=4)
    sched = Schedule(rule, nyc, ambiguous=BOTH)

    via_iter = sorted(sched)
    via_between = sched.between(utc(2024, 11, 3), utc(2024, 11, 4))

    assert via_iter == via_between


def test_invalid_arguments(nyc):
    rule = rrule(DAILY, dtstart=FALL, count=1)

    with pytest.raises(ValueError):
        Schedule(rule, nyc, nonexistent="bogus")
    with pytest.raises(ValueError):
        Schedule(rule, nyc, ambiguous="bogus")
    with pytest.raises(TypeError):
        Schedule(object(), nyc)
    with pytest.raises(ValueError):
        Schedule(rule, None)

    sched = Schedule(rule, nyc)
    with pytest.raises(ValueError):
        sched.between(utc(2024, 11, 4), utc(2024, 11, 3))


def test_aware_dtstart_rule_is_rejected(nyc):
    aware = rrule(
        DAILY, dtstart=datetime(2024, 3, 10, 2, 30, tzinfo=nyc), count=1
    )
    with pytest.raises(ValueError):
        Schedule(aware, nyc)
