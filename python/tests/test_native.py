from __future__ import annotations

import sqlite3
import unittest

from effectkit.reconcile import EffectError, reconcile, unwind
from effectkit.registry import bundled


def sqlite_with_row() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE orders (order_ref TEXT UNIQUE, amount INTEGER)")
    conn.execute("INSERT INTO orders (order_ref, amount) VALUES ('ORD-1', 4999)")
    conn.commit()
    return conn


class TestPostgresNativeHandlers(unittest.TestCase):
    """The Postgres handlers are DB-API 2.0 driver-agnostic, so sqlite exercises them."""

    def setUp(self):
        self.capsule = bundled().get("postgres.insert")

    def _ctx(self, conn, key_value):
        return {
            "connection": conn,
            "table": "orders",
            "key_column": "order_ref",
            "key_value": key_value,
            "paramstyle": "qmark"}

    def test_probe_landed_and_not_landed(self):
        conn = sqlite_with_row()
        self.assertEqual(reconcile(self.capsule, self._ctx(conn, "ORD-1")).status, "landed")
        self.assertEqual(reconcile(self.capsule, self._ctx(conn, "ORD-9")).status, "not_landed")

    def test_compensation_deletes_row(self):
        conn = sqlite_with_row()
        result = unwind(self.capsule, self._ctx(conn, "ORD-1"))
        self.assertEqual(result.status, "compensated")
        self.assertEqual(reconcile(self.capsule, self._ctx(conn, "ORD-1")).status, "not_landed")

    def test_compensation_on_missing_row_is_noop(self):
        conn = sqlite_with_row()
        result = unwind(self.capsule, self._ctx(conn, "ORD-9"))
        self.assertEqual(result.status, "no_compensation")

    def test_identifier_whitelist_blocks_injection(self):
        conn = sqlite_with_row()
        ctx = self._ctx(conn, "ORD-1")
        ctx["table"] = "orders; DROP TABLE orders"
        with self.assertRaises(EffectError) as raised:
            reconcile(self.capsule, ctx)
        self.assertIn("not a safe SQL identifier", str(raised.exception))

    def test_native_needs_connection(self):
        with self.assertRaises(EffectError) as raised:
            reconcile(self.capsule, {"table": "orders", "key_column": "order_ref", "key_value": "x"})
        self.assertIn("connection", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
