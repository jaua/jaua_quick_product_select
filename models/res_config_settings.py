from odoo import fields, models

from .quick_select_mixin import DEFAULT_HISTORY_MONTHS, DEFAULT_PRICE_POLICY, DEFAULT_SEARCH_LIMIT, PARAM_PREFIX


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    quick_select_history_months = fields.Integer(
        string="Frequent products period (months)",
        config_parameter=PARAM_PREFIX + 'history_months',
        default=DEFAULT_HISTORY_MONTHS,
    )
    quick_select_price_policy = fields.Selection(
        [('last_price', "Last price paid by the customer"), ('pricelist', "Customer pricelist")],
        string="Frequent products price",
        config_parameter=PARAM_PREFIX + 'price_policy',
        default=DEFAULT_PRICE_POLICY,
    )
    quick_select_search_limit = fields.Integer(
        string="Search results",
        config_parameter=PARAM_PREFIX + 'search_limit',
        default=DEFAULT_SEARCH_LIMIT,
    )
