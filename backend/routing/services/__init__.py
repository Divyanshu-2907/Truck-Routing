"""Pure-Python business logic for route risk scoring.

Modules in this package must not import Django. They take plain data in and
return plain data out, which keeps the routing, weather and risk rules easy
to unit test and easy to reason about.
"""
