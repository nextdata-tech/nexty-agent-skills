"""Filters on the source handover, pinned one at a time.

``advertised_endpoints`` decides what a scenario's generated
``infra-profile.yaml`` tells the agent about. Every clause in it is a
separate promise, but the shipped route table happens to be filtered by
more than one clause at once -- its only templated path is also a
forbidden write -- so a mutation that removes the templated-path clause
alone survives the whole suite. These tests exercise each clause against a
route that trips only that clause, so the suite notices when one stops
doing anything.

The property matters because this scenario grades honest probing: an
endpoint written into the handover is one the agent never has to discover,
and an error-only route named there would answer the very question the
drill exists to ask.
"""

from __future__ import annotations

from dataclasses import dataclass

from dp_scenarios.runner.environment import advertised_endpoints


@dataclass(frozen=True)
class _Route:
    """The attribute surface advertised_endpoints reads via getattr."""

    path: str
    method: str = "GET"
    status: int = 200
    write_forbidden: bool = False
    response: object = "{}"
    states: dict[str, object] | None = None


def test_a_plain_successful_get_is_advertised() -> None:
    assert advertised_endpoints([_Route("/deals")]) == ("/deals",)


def test_a_route_that_serves_no_body_is_not_advertised() -> None:
    assert advertised_endpoints([_Route("/deals", response=None)]) == ()


def test_a_templated_path_is_not_advertised_even_when_otherwise_eligible() -> None:
    """The clause under test is the only reason this route is excluded.

    A successful parameter-free GET is advertised; make the path templated
    and nothing else, and it must drop out. The shipped table cannot show
    this on its own because its templated route is also a forbidden write.
    """

    assert advertised_endpoints([_Route("/deals")]) == ("/deals",)
    assert advertised_endpoints([_Route("/deals/{id}")]) == ()


def test_a_non_get_method_is_not_advertised() -> None:
    assert advertised_endpoints([_Route("/deals", method="PATCH")]) == ()


def test_an_error_only_route_is_not_advertised() -> None:
    assert advertised_endpoints([_Route("/deals/history", status=404)]) == ()


def test_a_forbidden_write_is_not_advertised() -> None:
    assert advertised_endpoints([_Route("/deals", write_forbidden=True)]) == ()


def test_a_relative_path_is_not_advertised() -> None:
    assert advertised_endpoints([_Route("deals")]) == ()


def test_each_eligible_path_is_advertised_once_in_declaration_order() -> None:
    routes = [_Route("/deals"), _Route("/owners"), _Route("/deals")]
    assert advertised_endpoints(routes) == ("/deals", "/owners")
