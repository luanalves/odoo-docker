# -*- coding: utf-8 -*-

PUBLIC_PROPERTY_STATUSES = frozenset({"available", "rented", "sold", "reserved"})

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def parse_status_filter(raw_status):
    """Parse the optional `status` query param.

    Returns (status_values, ok). status_values is None when the param was
    omitted (no filter applied) or when validation failed. ok is False when
    any token is outside PUBLIC_PROPERTY_STATUSES.
    """
    if not raw_status:
        return None, True

    tokens = [token.strip() for token in raw_status.split(",") if token.strip()]
    if not tokens or any(token not in PUBLIC_PROPERTY_STATUSES for token in tokens):
        return None, False
    return tokens, True


def parse_ids_filter(raw_ids):
    """Parse the optional `ids` query param into a list of ints."""
    if not raw_ids:
        return None, True

    tokens = [token.strip() for token in raw_ids.split(",") if token.strip()]
    if not tokens:
        return None, True

    ids = []
    for token in tokens:
        try:
            ids.append(int(token))
        except ValueError:
            return None, False
    return ids, True


def parse_sort(raw_sort):
    """Parse the optional `sort` query param into an ORM order clause."""
    sort = raw_sort or "newest"
    if sort == "newest":
        return "create_date desc", True
    if sort == "oldest":
        return "create_date asc", True
    return None, False


def parse_limit(raw_limit):
    """Parse the optional `limit` query param: default 20, hard-clamped to 100."""
    if raw_limit is None or raw_limit == "":
        return DEFAULT_LIMIT, True
    try:
        limit = int(raw_limit)
    except ValueError:
        return None, False
    if limit <= 0:
        return None, False
    return min(limit, MAX_LIMIT), True


def build_public_property_domain(company_id, status_values=None, ids=None):
    """Build the search domain for the public property listing.

    Mandatory filters (company_id, active, publish_website) are always
    applied first and cannot be overridden by any query param.
    """
    domain = [
        ("company_id", "=", company_id),
        ("active", "=", True),
        ("publish_website", "=", True),
    ]
    if status_values:
        domain.append(("property_status", "in", status_values))
    if ids:
        domain.append(("id", "in", ids))
    return domain
