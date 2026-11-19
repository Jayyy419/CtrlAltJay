"""A monthly spending cap for owner-side Claude API calls.

Before a request is sent, its worst-case cost is added to the month's row
with a conditional write, so two requests at once can't take the month over
the cap. Afterwards the reservation is swapped for what the request really
cost, or refunded if it failed.
"""
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError


class OverBudget(Exception):
    pass


def month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _dec(value):
    return Decimal(str(round(value, 6)))


def reserve(table, key, cap, worst_case):
    try:
        table.update_item(
            Key=key, UpdateExpression="ADD spent_usd :r",
            ConditionExpression="attribute_not_exists(spent_usd) OR spent_usd <= :limit",
            ExpressionAttributeValues={":r": _dec(worst_case), ":limit": _dec(cap - worst_case)},
        )
    except ClientError as err:
        if err.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise OverBudget() from None
        raise


def settle(table, key, actual, worst_case, count_field="calls"):
    table.update_item(Key=key, UpdateExpression=f"ADD spent_usd :d, {count_field} :one",
                      ExpressionAttributeValues={":d": _dec(actual) - _dec(worst_case), ":one": 1})


def spent(table, key, count_field="calls"):
    item = table.get_item(Key=key).get("Item") or {}
    return float(item.get("spent_usd", 0)), int(item.get(count_field, 0))
