"""Concrete eval scenarios that wire real meshes into ``nxd_eval`` suites.

Each module here describes ONE target (a mesh, a credential path, a case set) and
drives it through the framework's ``run_suite`` — it is not reusable machinery.
Keeping scenarios in their own package keeps the framework root (``src/nxd_eval``)
free of one-off wiring.
"""
