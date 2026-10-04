"""
Schedule adapter that expands local-wall-clock :py:class:`dateutil.rrule`
recurrence rules into absolute UTC instants with explicit handling of
daylight-saving-time (DST) gaps and folds.

A recurrence rule expressed in *local wall time* does not by itself define a
unique UTC instant:

* In a "spring forward" gap, some wall-clock times **do not exist**.
* In a "fall back" fold, some wall-clock times **occur twice**.

This module leaves all calendar arithmetic to :py:mod:`dateutil.rrule` and
:py:mod:`dateutil.tz`; it only resolves the local candidates those produce
onto the UTC timeline.  See :py:func:`occurrences`.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum

from dateutil import rrule as _rrule
from dateutil.tz import gettz as _gettz

__all__ = ["GapPolicy", "FoldPolicy", "occurrences"]


class GapPolicy(Enum):
    """How to resolve a wall-clock time that does not exist (a DST gap)."""

    SKIP = "skip"
    """Discard the occurrence entirely."""

    FORWARD = "forward"
    """Move it to the first valid wall-clock instant (the gap end)."""


class FoldPolicy(Enum):
    """How to resolve a wall-clock time that occurs twice (a DST fold)."""

    EARLIEST = "earliest"
    """Keep only the first occurrence (pre-transition / larger offset)."""

    LATEST = "latest"
    """Keep only the second occurrence (post-transition / smaller offset)."""

    BOTH = "both"
    """Keep both occurrences, one hour apart for a one-hour DST change."""


# Amount of wall-clock time inspected on each side of the requested UTC
# range when gathering local candidates. Must exceed any possible DST
# transition size plus rule interval, so a gap "forward" result and the
# second leg of a fold that land just inside the range are not missed.
_PADDING = timedelta(hours=48)


def _as_utc(dt, name):
    """Normalize an aware datetime to UTC; reject naive datetimes."""
    if not isinstance(dt, datetime):
        raise TypeError("%s must be a datetime.datetime instance" % name)
    if dt.tzinfo is None:
        raise ValueError("%s must be timezone-aware (UTC)" % name)
    return dt.astimezone(timezone.utc)


def _resolve_tz(tz):
    """Accept a tzinfo object or an IANA zone name."""
    if isinstance(tz, str):
        return _gettz(tz)
    if tz is None:
        raise ValueError("a timezone (tzinfo or zone name) is required")
    return tz


def _first_valid_instant(wall_naive, tz):
    """
    Return the earliest UTC instant whose local label in *tz* is not earlier
    than *wall_naive* (a naive local datetime known to fall in a gap).

    This is the wall-clock instant at which time becomes valid again.  The
    transition point is found by binary search over UTC instants: the local
    label as a function of UTC is strictly increasing once the gap is
    bracketed, so the first instant with ``label >= wall_naive`` is the gap
    end.  No calendar or transition-table arithmetic is reimplemented.
    """
    anchor = wall_naive.replace(tzinfo=tz, fold=0).astimezone(timezone.utc)

    def label(utc_dt):
        return utc_dt.astimezone(tz).replace(tzinfo=None)

    # Grow outward until the bracket straddles the gap: the lower local
    # label precedes the missing time and the upper one reaches it.
    lo = anchor - _PADDING
    hi = anchor + _PADDING
    while label(lo) >= wall_naive:
        lo -= _PADDING
    while label(hi) < wall_naive:
        hi += _PADDING

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def us(utc_dt):
        return int((utc_dt - epoch) // timedelta(microseconds=1))

    lo_us, hi_us = us(lo), us(hi)

    def label_at(microseconds):
        return label(epoch + timedelta(microseconds=microseconds))

    # Smallest integer microsecond whose local label reaches wall_naive.
    while lo_us < hi_us:
        mid_us = (lo_us + hi_us) // 2
        if label_at(mid_us) < wall_naive:
            lo_us = mid_us + 1
        else:
            hi_us = mid_us
    return epoch + timedelta(microseconds=lo_us)


def occurrences(
    rule,
    tz,
    range_start,
    range_end,
    gap_policy=GapPolicy.SKIP,
    fold_policy=FoldPolicy.BOTH,
):
    """
    Expand a local-wall-clock recurrence rule into UTC instants.

    :param rule: a :py:class:`dateutil.rrule.rrule` or
        :py:class:`dateutil.rrule.rruleset` built with **naive** datetimes
        whose values are wall-clock times in *tz*.
    :param tz: the timezone in which the rule's wall-clock times are
        interpreted, given as a :class:`~datetime.tzinfo` or an IANA zone
        name (e.g. ``"America/New_York"``).
    :param range_start: aware datetime marking the inclusive UTC start of
        the half-open query interval.
    :param range_end: aware datetime marking the exclusive UTC end of the
        half-open query interval.
    :param gap_policy: how to treat non-existent wall-clock times, a
        :class:`GapPolicy` member (or its value string).
    :param fold_policy: how to treat duplicated wall-clock times, a
        :class:`FoldPolicy` member (or its value string).

    :returns: a list of timezone-aware UTC
        :class:`~datetime.datetime` instances, sorted ascending, with no
        duplicates.

    Range filtering is performed on the **UTC timeline** using a half-open
    ``[range_start, range_end)`` interval.  Wall-clock comparison is never
    used, so the second leg of an ambiguous ("fall back") occurrence is not
    lost.

    .. note::

       Rule count versus output count.  A rule's ``COUNT`` limits the number
       of *local candidates* generated by dateutil; the number of returned
       UTC instants may differ. :py:data:`GapPolicy.SKIP` drops candidates,
       :py:data:`GapPolicy.FORWARD` may move a candidate onto another
       instant (duplicates are removed), and :py:data:`FoldPolicy.BOTH` can
       emit **two** UTC instants for a single candidate.
    """
    if not isinstance(rule, (_rrule.rrule, _rrule.rruleset)):
        raise TypeError("rule must be a dateutil.rrule.rrule or rruleset")
    dtstart = getattr(rule, "_dtstart", None)
    if dtstart is not None and dtstart.tzinfo is not None:
        raise ValueError(
            "rule must be defined with naive local datetimes; "
            "the timezone is supplied separately"
        )
    until = getattr(rule, "_until", None)
    if until is not None and until.tzinfo is not None:
        raise ValueError("UNTIL must be a naive local datetime")

    tzinfo = _resolve_tz(tz)
    utc_start = _as_utc(range_start, "range_start")
    utc_end = _as_utc(range_end, "range_end")
    if utc_start > utc_end:
        raise ValueError("range_start must not be after range_end")

    gap_policy = GapPolicy(gap_policy)
    fold_policy = FoldPolicy(fold_policy)

    # Gather local candidates over a padded window so that gap-forwards and
    # the second leg of a fold mapping just inside the UTC range survive.
    win_lo = utc_start.astimezone(tzinfo).replace(tzinfo=None) - _PADDING
    win_hi = utc_end.astimezone(tzinfo).replace(tzinfo=None) + _PADDING
    candidates = rule.between(win_lo, win_hi, inc=True)

    instants = set()
    for wall in candidates:
        first = wall.replace(tzinfo=tzinfo, fold=0)
        second = wall.replace(tzinfo=tzinfo, fold=1)
        off0 = first.utcoffset()
        off1 = second.utcoffset()

        if off0 == off1:
            # Unambiguous time, or a gap (dateutil gives both folds the same
            # post-transition offset inside a gap). Tell them apart by
            # round-tripping through UTC.
            roundtrip = (
                first.astimezone(timezone.utc)
                .astimezone(tzinfo)
                .replace(tzinfo=None)
            )
            if roundtrip != wall:
                # Non-existent local time ("spring forward" gap).
                if gap_policy is GapPolicy.FORWARD:
                    instants.add(_first_valid_instant(wall, tzinfo))
                # GapPolicy.SKIP: discard.
            else:
                instants.add(first.astimezone(timezone.utc))
        elif off0 > off1:
            # Ambiguous local time ("fall back"): fold=0 is the earlier leg
            # (larger offset, e.g. EDT -4); fold=1 the later leg (EST -5).
            if fold_policy in (FoldPolicy.EARLIEST, FoldPolicy.BOTH):
                instants.add(first.astimezone(timezone.utc))
            if fold_policy in (FoldPolicy.LATEST, FoldPolicy.BOTH):
                instants.add(second.astimezone(timezone.utc))
        else:
            # Defensive: off0 < off1 is never a label on the real timeline;
            # treat it as a gap rather than emitting an impossible instant.
            if gap_policy is GapPolicy.FORWARD:
                instants.add(_first_valid_instant(wall, tzinfo))

    return sorted(dt for dt in instants if utc_start <= dt < utc_end)
