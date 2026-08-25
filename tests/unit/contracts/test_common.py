from __future__ import annotations

import unittest

from veyra_agent_platform.contracts.common import (
    SCHEMA_VERSION,
    ContractValidationError,
    IdempotencyKey,
    new_uuid7,
    require_uuid7,
)


class CommonContractTests(unittest.TestCase):
    def test_generated_uuid7_is_lowercase_and_valid(self) -> None:
        first = new_uuid7()
        second = new_uuid7()
        self.assertEqual(first[14], "7")
        self.assertIn(second[19], "89ab")
        self.assertEqual(require_uuid7(first, "id"), first)
        self.assertNotEqual(first, second)

    def test_idempotency_key_rejects_non_uuid7(self) -> None:
        with self.assertRaises(ContractValidationError):
            IdempotencyKey(SCHEMA_VERSION, "request-1")
