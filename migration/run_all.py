"""Orchestrator: run all four imports in the correct order.

Order matters: customers -> orders (orders link to customer); prospects and
activities are independent.
"""
from __future__ import annotations

import import_customers
import import_prospects
import import_orders
import import_activities


def main() -> None:
    import_customers.main()
    import_prospects.main()
    import_orders.main()
    import_activities.main()


if __name__ == "__main__":
    main()
