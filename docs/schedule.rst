=====================
schedule
=====================

.. automodule:: dateutil.schedule
   :members: GapPolicy, FoldPolicy, occurrences


Overview
========

``dateutil.schedule`` adapts a recurrence rule expressed in **local wall
time** to a stream of absolute **UTC instants**.  All calendar arithmetic is
performed by :mod:`dateutil.rrule` and :mod:`dateutil.tz`; this adapter only
decides how wall-clock candidates that are ambiguous or invalid due to
daylight-saving time map onto the UTC timeline.

A local recurrence rule can hit two kinds of problematic wall-clock times:

* A **gap** ("spring forward"): a wall-clock time that never happens.  Use
  :class:`~dateutil.schedule.GapPolicy` to either :py:data:`~GapPolicy.SKIP`
  it or move it :py:data:`~GapPolicy.FORWARD` to the first valid instant
  (typically ``03:00`` when clocks jump from ``02:00`` to ``03:00``).
* A **fold** ("fall back"): a wall-clock time that happens twice.  Use
  :class:`~dateutil.schedule.FoldPolicy` to keep the
  :py:data:`~FoldPolicy.EARLIEST` occurrence, the
  :py:data:`~FoldPolicy.LATEST` occurrence, or :py:data:`~FoldPolicy.BOTH`.

The query range is always interpreted on the UTC timeline as a **half-open**
``[range_start, range_end)`` interval.  Filtering is never done in wall-clock
time, so the second leg of a folded occurrence that falls in range is never
dropped.  The returned datetimes are timezone-aware (UTC), sorted ascending,
and contain no duplicates; a gap-forward that lands on another generated
instant is de-duplicated.

Build the rule with naive datetimes and pass the timezone separately:

.. doctest::

    >>> from datetime import datetime, timezone
    >>> from dateutil import rrule
    >>> from dateutil.schedule import occurrences, GapPolicy, FoldPolicy

Fall-back fold, both legs kept (they are one hour apart in UTC):

.. doctest::

    >>> rule = rrule.rrule(rrule.DAILY,
    ...                    dtstart=datetime(2024, 11, 2, 1, 30),
    ...                    until=datetime(2024, 11, 4, 1, 30))
    >>> occurrences(rule, "America/New_York",  # doctest: +NORMALIZE_WHITESPACE
    ...             datetime(2024, 11, 2, tzinfo=timezone.utc),
    ...             datetime(2024, 11, 5, tzinfo=timezone.utc),
    ...             fold_policy=FoldPolicy.BOTH)
    [datetime.datetime(2024, 11, 2, 5, 30, tzinfo=datetime.timezone.utc),
     datetime.datetime(2024, 11, 3, 5, 30, tzinfo=datetime.timezone.utc),
     datetime.datetime(2024, 11, 3, 6, 30, tzinfo=datetime.timezone.utc),
     datetime.datetime(2024, 11, 4, 6, 30, tzinfo=datetime.timezone.utc)]

Spring-forward gap, skipped or moved forward to ``03:00 EDT`` (``07:00Z``):

.. doctest::

    >>> rule = rrule.rrule(rrule.DAILY,
    ...                    dtstart=datetime(2024, 3, 9, 2, 30),
    ...                    until=datetime(2024, 3, 11, 2, 30))
    >>> occurrences(rule, "America/New_York",  # doctest: +NORMALIZE_WHITESPACE
    ...             datetime(2024, 3, 9, tzinfo=timezone.utc),
    ...             datetime(2024, 3, 12, tzinfo=timezone.utc),
    ...             gap_policy=GapPolicy.SKIP)
    [datetime.datetime(2024, 3, 9, 7, 30, tzinfo=datetime.timezone.utc),
     datetime.datetime(2024, 3, 11, 6, 30, tzinfo=datetime.timezone.utc)]
    >>> occurrences(rule, "America/New_York",  # doctest: +NORMALIZE_WHITESPACE
    ...             datetime(2024, 3, 9, tzinfo=timezone.utc),
    ...             datetime(2024, 3, 12, tzinfo=timezone.utc),
    ...             gap_policy=GapPolicy.FORWARD)
    [datetime.datetime(2024, 3, 9, 7, 30, tzinfo=datetime.timezone.utc),
     datetime.datetime(2024, 3, 10, 7, 0, tzinfo=datetime.timezone.utc),
     datetime.datetime(2024, 3, 11, 6, 30, tzinfo=datetime.timezone.utc)]


Rule COUNT versus output count
==============================

A rule's ``COUNT`` (and ``UNTIL``) governs the number of **local candidates**
that :mod:`dateutil.rrule` generates.  It is **not** the number of UTC
instants returned by :func:`~dateutil.schedule.occurrences`:

* :py:data:`~GapPolicy.SKIP` can make the output *shorter* (gap candidates
  are removed),
* :py:data:`~FoldPolicy.BOTH` can make the output *longer* (one ambiguous
  candidate yields two UTC instants),
* :py:data:`~GapPolicy.FORWARD` can also make the output shorter when the
  forwarded instant collides with another candidate, because results are
  de-duplicated,
* and the UTC range itself filters the resolved instants.

For example, ``COUNT=3`` across a fall-back day with
``fold_policy=FoldPolicy.BOTH`` returns four UTC instants.
