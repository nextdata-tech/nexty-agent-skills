"""Synthetic monthly workforce snapshots for the B6 headcount scenario."""

from __future__ import annotations

import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition, InjectorSpec
from ..defects import Frame
from ..registry import register_dataset


_SNAPSHOTS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "2023-12": {
        "Engineering": tuple(f"E{number:03d}" for number in range(1, 7)),
        "Sales": tuple(f"S{number:03d}" for number in range(1, 9)),
        "Research": tuple(f"R{number:03d}" for number in range(1, 4)),
    },
    "2024-01": {
        "Engineering": tuple(f"E{number:03d}" for number in range(1, 7)),
        "Sales": tuple(f"S{number:03d}" for number in range(1, 8)),
        "Research": tuple(f"R{number:03d}" for number in range(1, 4)),
    },
    "2024-02": {
        "Engineering": tuple(f"E{number:03d}" for number in range(1, 8)),
        "Sales": tuple(f"S{number:03d}" for number in range(1, 8)) + ("S009",),
        "Research": tuple(f"R{number:03d}" for number in range(1, 4)),
    },
    "2024-03": {
        "Engineering": ("E001", "E002", "E003", "E004", "E005", "E007"),
        "Sales": tuple(f"S{number:03d}" for number in range(1, 8)) + ("S009",),
        "Research": ("R001", "R002"),
    },
}


def _build_headcount_attrition(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    """Build reproducible month snapshots with opaque cross-month tokens."""

    del seed
    employee_tokens: dict[str, str] = {}
    rows: Frame = []
    for month, departments in _SNAPSHOTS.items():
        for department, employee_codes in departments.items():
            for employee_code in employee_codes:
                token = employee_tokens.get(employee_code)
                if token is None:
                    token = f"person-{rng.getrandbits(128):032x}"
                    employee_tokens[employee_code] = token
                employee_number = int(employee_code[1:])
                rows.append(
                    {
                        "snapshot_month": month,
                        "department": department,
                        "opaque_person_token": token,
                        "full_name": f"Synthetic Person {employee_code}",
                        "email": f"{employee_code.lower()}@workforce.example.invalid",
                        "salary_eur": f"{42_000 + employee_number * 375:,.2f}",
                    }
                )
    return {"hr_export": rows}


register_dataset(
    DatasetDefinition(
        name="headcount_attrition",
        base_instant=BASE_INSTANT,
        table_columns={
            "hr_export": (
                "snapshot_month",
                "department",
                "opaque_person_token",
                "full_name",
                "email",
                "salary_eur",
            ),
        },
        injectors=(
            InjectorSpec(
                "hr_export",
                "pii_sentinels",
                {"columns": ["full_name", "email", "salary_eur"]},
            ),
        ),
        builder=_build_headcount_attrition,
        description="Monthly workforce snapshots with period, department, and employment records.",
        plant="B6-suppression-N",
        requires_explicit_plant=True,
    )
)
