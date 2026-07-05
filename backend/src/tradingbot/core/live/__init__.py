"""Tick-level trading logic for the paper/live runner — pure, no I/O.

The counterpart of core/backtest: the same TradeRules and the same shared
barrier/sizing helpers (core.backtest.engine), applied one closed bar at a
time with state that survives process restarts. The top-level live/ package
is the *process* (scheduler, wiring); this package is the *logic*.
"""
