========
schedule
========

.. automodule:: dateutil.schedule
   :members:
   :undoc-members:

Schedule examples
-----------------

A :class:`~dateutil.schedule.Schedule` is built from a *local*
:class:`~dateutil.rrule.rrule` (naive wall-clock candidates), a time zone,
and two strategy choices for the wall-clock times that do not behave:

* ``nonexistent`` -- what to do with wall-clock times that do not exist
  because the clocks jumped forward (spring-forward gaps):
  :data:`~dateutil.schedule.SKIP` (drop the candidate) or
  :data:`~dateutil.schedule.SHIFT` (move it forward to the first valid
  instant).
* ``ambiguous`` -- what to do with wall-clock times that occur twice
  because the clocks fell back (fall-back overlaps):
  :data:`~dateutil.schedule.EARLIER` (the DST offset),
  :data:`~dateutil.schedule.LATER` (the standard offset) or
  :data:`~dateutil.schedule.BOTH` (both instants).

The examples below use a POSIX rule equivalent to ``America/New_York``
(the same transition dates); with a full zoneinfo database you would use
``tz.gettz('America/New_York')``.

.. testsetup:: schedule

    from datetime import datetime
    from dateutil import tz
    from dateutil.rrule import rrule, DAILY, HOURLY
    from dateutil.schedule import Schedule, SKIP, SHIFT, EARLIER, LATER, BOTH
    NYC = tz.tzstr('EST5EDT4,M3.2.0/2,M11.1.0/2')

Spring forward: a nonexistent wall-clock time
=============================================

On 2024-03-10 in New York the clocks jump from 02:00 to 03:00, so 02:30
never happens.  With ``SKIP`` the candidate is dropped; with ``SHIFT`` it
is moved forward to 03:30 wall clock (07:30 UTC):

.. doctest:: schedule

    >>> rule = rrule(DAILY, dtstart=datetime(2024, 3, 10, 2, 30), count=1)
    >>> sched = Schedule(rule, NYC, nonexistent=SKIP)
    >>> sched.between(datetime(2024, 3, 10, tzinfo=tz.UTC),
    ...               datetime(2024, 3, 11, tzinfo=tz.UTC))
    []

    >>> sched = Schedule(rule, NYC, nonexistent=SHIFT)
    >>> out = sched.between(datetime(2024, 3, 10, tzinfo=tz.UTC),
    ...                     datetime(2024, 3, 11, tzinfo=tz.UTC))
    >>> [dt.isoformat() for dt in out]
    ['2024-03-10T07:30:00+00:00']

Fall back: an ambiguous wall-clock time
=======================================

On 2024-11-03 in New York the clocks go from EDT back to EST, so 01:30
happens twice -- at 05:30 UTC (EDT) and 06:30 UTC (EST), exactly one hour
apart:

.. doctest:: schedule

    >>> rule = rrule(DAILY, dtstart=datetime(2024, 11, 3, 1, 30), count=1)
    >>> earlier = Schedule(rule, NYC, ambiguous=EARLIER)
    >>> later = Schedule(rule, NYC, ambiguous=LATER)
    >>> both = Schedule(rule, NYC, ambiguous=BOTH)
    >>> rng = (datetime(2024, 11, 3, tzinfo=tz.UTC),
    ...        datetime(2024, 11, 4, tzinfo=tz.UTC))
    >>> [dt.isoformat() for dt in earlier.between(*rng)]
    ['2024-11-03T05:30:00+00:00']
    >>> [dt.isoformat() for dt in later.between(*rng)]
    ['2024-11-03T06:30:00+00:00']
    >>> [dt.isoformat() for dt in both.between(*rng)]
    ['2024-11-03T05:30:00+00:00', '2024-11-03T06:30:00+00:00']

The range is a UTC half-open interval ``[start, end)``: the start instant
is included, the end instant is excluded.  Filtering happens on the
localized UTC instants, so the second occurrence is never lost:

.. doctest:: schedule

    >>> # 05:30 UTC is included (start inclusive)...
    >>> out = both.between(datetime(2024, 11, 3, 5, 30, tzinfo=tz.UTC),
    ...                    datetime(2024, 11, 3, 6, 30, tzinfo=tz.UTC))
    >>> [dt.isoformat() for dt in out]
    ['2024-11-03T05:30:00+00:00']
    >>> # ...and 06:30 UTC is excluded (end exclusive).
    >>> both.between(datetime(2024, 11, 3, 5, 31, tzinfo=tz.UTC),
    ...              datetime(2024, 11, 3, 6, 30, tzinfo=tz.UTC))
    []

De-duplication of shifted candidates
====================================

A shifted imaginary time can land on top of another candidate.  The
hourly rule below fires at 00:30, 01:30, 02:30, 03:30 and 04:30.  The
02:30 candidate is shifted to 03:30 wall clock -- the same UTC instant as
the real 03:30 candidate -- so the output contains four unique instants:

.. doctest:: schedule

    >>> rule = rrule(HOURLY, dtstart=datetime(2024, 3, 10, 0, 30), count=5)
    >>> sched = Schedule(rule, NYC, nonexistent=SHIFT)
    >>> out = sched.between(datetime(2024, 3, 10, tzinfo=tz.UTC),
    ...                     datetime(2024, 3, 11, tzinfo=tz.UTC))
    >>> [dt.isoformat() for dt in out]
    ['2024-03-10T05:30:00+00:00', '2024-03-10T06:30:00+00:00', '2024-03-10T07:30:00+00:00', '2024-03-10T08:30:00+00:00']

Rule count vs. output count
===========================

``COUNT`` (and ``UNTIL``) limits the number of *wall-clock candidates*
the rule generates; it does **not** limit the number of output instants.
An ambiguous candidate produces two outputs, a skipped candidate produces
none, and a shifted candidate that collides with another produces one
after de-duplication:

.. doctest:: schedule

    >>> # COUNT=4 candidates, but the 01:30 candidate doubles under BOTH.
    >>> rule = rrule(HOURLY, dtstart=datetime(2024, 11, 3, 0, 30), count=4)
    >>> rule.count()
    4
    >>> sched = Schedule(rule, NYC, ambiguous=BOTH)
    >>> out = sched.between(datetime(2024, 11, 3, tzinfo=tz.UTC),
    ...                     datetime(2024, 11, 4, tzinfo=tz.UTC))
    >>> len(out)
    5
