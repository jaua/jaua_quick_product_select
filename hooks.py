import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Enable the PostgreSQL ``unaccent`` extension used by the quick search.

    Only this module uses it (see ``quick.select.mixin._quick_search_product_ids``);
    Odoo's global ``unaccent`` option is left untouched. ``unaccent`` is a
    trusted extension since PostgreSQL 13, so the database owner can create it.
    If it cannot be created, the search falls back to accent-sensitive matching.
    """
    try:
        with env.cr.savepoint():
            env.cr.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    except Exception as error:  # noqa: BLE001 - any failure only degrades the search
        _logger.warning(
            "Could not enable the unaccent extension; quick search will be "
            "accent-sensitive: %s", error,
        )
