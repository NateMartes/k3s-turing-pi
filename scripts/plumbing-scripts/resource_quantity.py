#!/usr/bin/env python3
import argparse
from decimal import Decimal, InvalidOperation
import re


QUANTITY = re.compile(r"((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)(?:n|u|m|[kKMGTPE]i?)?")


def resource_quantity(value: str) -> str:
    match = QUANTITY.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError(
            "must be a Kubernetes resource quantity, for example 2, 500m, 6Gi, or 10Gi"
        )
    try:
        is_zero = Decimal(match.group(1)) == 0
    except InvalidOperation:
        is_zero = True
    if is_zero:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value
