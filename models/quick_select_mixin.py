import re

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

PARAM_PREFIX = 'jaua_quick_product_select.'
DEFAULT_HISTORY_MONTHS = 12
DEFAULT_SEARCH_LIMIT = 8
DEFAULT_PRICE_POLICY = 'last_price'
# Maximum number of products listed in "Frequent products".
FREQUENT_LIMIT = 50
# Extra candidates fetched by the raw SQL search, so that products later
# filtered out by record rules do not leave the result list short.
SEARCH_CANDIDATE_FACTOR = 5

# "3 rj45", "3x rj45", "3 x rj45", "2.5 cable": quantity, optional x, then the term.
# A term without spaces ("880030081", "3xm") is never read as a quantity.
QTY_PATTERN = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*[x×]?\s+(\S.*)$', re.IGNORECASE)


class QuickSelectMixin(models.AbstractModel):
    """Quick product selection for documents with product lines.

    Holds the logic shared by every document type. The concrete model (see
    ``sale_order.py``) sets the ``_quick_*`` attributes and overrides the
    hooks; a purchase order would only need its own values for them.
    """
    _name = 'quick.select.mixin'
    _description = 'Quick product selection'

    # Line model and its fields.
    _quick_line_model = None
    _quick_line_qty_field = None
    _quick_line_uom_field = None
    # product.template boolean that allows the product on this document type.
    _quick_product_ok_field = None
    # Document states counted as purchase history / allowed to add lines.
    _quick_confirmed_states = ()
    _quick_editable_states = ()

    # ------------------------------------------------------------------
    # Settings and checks
    # ------------------------------------------------------------------

    @api.model
    def _quick_get_param(self, key, default):
        # sudo: ir.config_parameter is only readable by administrators, and
        # these values are plain module settings, not sensitive data.
        return self.env['ir.config_parameter'].sudo().get_param(PARAM_PREFIX + key, default)

    @api.model
    def _quick_settings(self):
        def positive_int(key, default):
            try:
                value = int(self._quick_get_param(key, default))
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        policy = self._quick_get_param('price_policy', DEFAULT_PRICE_POLICY)
        return {
            'history_months': positive_int('history_months', DEFAULT_HISTORY_MONTHS),
            'search_limit': positive_int('search_limit', DEFAULT_SEARCH_LIMIT),
            'price_policy': policy if policy in ('last_price', 'pricelist') else DEFAULT_PRICE_POLICY,
        }

    def _quick_check_editable(self):
        self.ensure_one()
        if self.state not in self._quick_editable_states:
            raise UserError(_("Quick selection is only available for quotations that are not confirmed yet."))

    # ------------------------------------------------------------------
    # Hooks for the concrete document
    # ------------------------------------------------------------------

    def _quick_commercial_partner(self):
        return self.partner_id.commercial_partner_id

    def _quick_line_base_domain(self):
        """Lines that represent a real product purchase (no sections, notes...)."""
        return [('display_type', '=', False), ('product_id', '!=', False)]

    def _quick_history_domain(self, partner=None):
        """Confirmed lines of the period, optionally restricted to one customer."""
        self.ensure_one()
        months = self._quick_settings()['history_months']
        date_from = fields.Datetime.now() - relativedelta(months=months)
        domain = self._quick_line_base_domain() + [
            ('state', 'in', list(self._quick_confirmed_states)),
            ('order_id.date_order', '>=', date_from),
            ('company_id', '=', self.company_id.id),
            ('order_id', '!=', self.id),
        ]
        if partner:
            domain.append(('order_id.partner_id.commercial_partner_id', '=', partner.id))
        return domain

    def _quick_product_domain(self):
        return [
            (self._quick_product_ok_field, '=', True),
            ('type', '!=', 'combo'),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ]

    def _quick_pricelist_prices(self, products, qty):
        """Unit price of each product for ``qty`` in the document currency."""
        raise NotImplementedError

    def _quick_mergeable_lines(self, product):
        """Existing lines a new quantity of ``product`` may be added to."""
        return self[self._quick_line_field()].filtered(
            lambda line: line.product_id == product
            and not line.display_type
            and line[self._quick_line_uom_field] == product.uom_id
        )

    def _quick_expected_price(self, product, qty):
        """Unit price a new line would get, to decide whether lines can merge."""
        raise NotImplementedError

    def _quick_line_field(self):
        return 'order_line'

    # ------------------------------------------------------------------
    # Model A: frequent products of the customer
    # ------------------------------------------------------------------

    def quick_get_frequent_products(self):
        self.ensure_one()
        settings = self._quick_settings()
        result = {'products': [], 'last_order': False, 'price_policy': settings['price_policy']}
        partner = self._quick_commercial_partner()
        if not partner:
            return result

        Line = self.env[self._quick_line_model]
        domain = self._quick_history_domain(partner) + [
            ('product_id.active', '=', True),
            ('product_id.' + self._quick_product_ok_field, '=', True),
        ]
        groups = Line._read_group(
            domain, ['product_id'], ['order_id:count_distinct'],
            order='order_id:count_distinct desc, product_id', limit=FREQUENT_LIMIT,
        )
        if not groups:
            return result
        products = self.env['product.product'].concat(*(product for product, _count in groups))

        # Latest line of each product: lines are sorted by their order
        # (sale.order._order = 'date_order desc, id desc'), so the first line
        # seen per product is the most recent one.
        last_lines = {}
        for line in Line.search(domain + [('product_id', 'in', products.ids)], order='order_id, id desc'):
            last_lines.setdefault(line.product_id, line)

        list_prices = self._quick_pricelist_prices(products, 1.0)
        for product, times in groups:
            line = last_lines.get(product)
            last_price = line and line.currency_id._convert(
                line.price_unit, self.currency_id, self.company_id,
                line.order_id.date_order or fields.Date.today(),
            )
            list_price = list_prices.get(product.id, 0.0)
            use_last = settings['price_policy'] == 'last_price' and line
            result['products'].append({
                'product_id': product.id,
                'name': product.display_name,
                'default_code': product.default_code or '',
                'times': times,
                'last_date': line and fields.Datetime.to_string(line.order_id.date_order),
                'last_price': last_price or 0.0,
                'list_price': list_price,
                'price': last_price if use_last else list_price,
                'uom': product.uom_id.name,
            })

        last_order = self._quick_last_order(partner)
        if last_order:
            result['last_order'] = {
                'id': last_order.id,
                'name': last_order.name,
                'date': fields.Datetime.to_string(last_order.date_order),
            }
        return result

    def _quick_last_order(self, partner):
        self.ensure_one()
        return self.search([
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('state', 'in', list(self._quick_confirmed_states)),
            ('company_id', '=', self.company_id.id),
            ('id', '!=', self.id),
        ], order='date_order desc, id desc', limit=1)

    def quick_repeat_last_order(self):
        """Add every product line of the customer's last confirmed order."""
        self.ensure_one()
        self._quick_check_editable()
        partner = self._quick_commercial_partner()
        last_order = partner and self._quick_last_order(partner)
        if not last_order:
            raise UserError(_("This customer has no confirmed orders to repeat."))

        use_last_price = self._quick_settings()['price_policy'] == 'last_price'
        allowed = self.env['product.product'].search(
            [('id', 'in', last_order[self._quick_line_field()].product_id.ids)] + self._quick_product_domain()
        )
        items = []
        for line in last_order[self._quick_line_field()].filtered_domain(self._quick_line_base_domain()):
            product = line.product_id
            if product not in allowed:
                continue
            qty = line[self._quick_line_uom_field]._compute_quantity(
                line[self._quick_line_qty_field], product.uom_id,
            )
            item = {'product_id': product.id, 'qty': qty}
            if use_last_price:
                item['price_unit'] = line.currency_id._convert(
                    line.price_unit, self.currency_id, self.company_id,
                    last_order.date_order or fields.Date.today(),
                )
            items.append(item)
        if not items:
            raise UserError(_("The last order of this customer has no products that can be added."))
        result = self.quick_add_lines(items)
        result['source_order'] = last_order.name
        return result

    # ------------------------------------------------------------------
    # Model B: command search
    # ------------------------------------------------------------------

    @api.model
    def _quick_parse_term(self, term):
        """Split ``"3 rj45"`` / ``"3x rj45"`` into ``(3.0, "rj45")``."""
        term = (term or '').strip()
        match = QTY_PATTERN.match(term)
        if match:
            qty = float(match.group(1).replace(',', '.'))
            if qty > 0:
                return qty, match.group(2).strip()
        return 1.0, term

    @api.model
    def _quick_has_unaccent(self):
        self.env.cr.execute("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'")
        return bool(self.env.cr.fetchone())

    def _quick_search_product_ids(self, text, limit):
        """Product ids whose name, internal reference or barcode contain every
        word of ``text``, ignoring case and accents.

        Raw SQL is used only to apply ``unaccent`` to the translated name; the
        candidates go through a regular ``search`` afterwards, so access rights
        and record rules still decide what the user gets.
        """
        words = text.split()
        if not words:
            return []

        if self._quick_has_unaccent():
            def norm(expr):
                return SQL("unaccent(%s)", expr)
        else:
            def norm(expr):
                return expr

        lang = self.env.lang or 'en_US'
        name = SQL("COALESCE(pt.name->>%s, pt.name->>'en_US')", lang)
        conditions = []
        for word in words:
            pattern = '%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            conditions.append(SQL(
                "(%s ILIKE %s OR %s ILIKE %s OR %s ILIKE %s)",
                norm(name), norm(SQL("%s", pattern)),
                norm(SQL("COALESCE(pp.default_code, '')")), norm(SQL("%s", pattern)),
                norm(SQL("COALESCE(pp.barcode, '')")), norm(SQL("%s", pattern)),
            ))
        self.env.cr.execute(SQL(
            """
            SELECT pp.id
              FROM product_product pp
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE pp.active AND pt.active AND %(ok)s
               AND pt.type != 'combo'
               AND (pt.company_id IS NULL OR pt.company_id = %(company)s)
               AND %(conditions)s
             ORDER BY lower(pp.default_code) = lower(%(text)s) DESC, %(name)s, pp.id
             LIMIT %(limit)s
            """,
            ok=SQL.identifier('pt', self._quick_product_ok_field),
            company=self.company_id.id,
            conditions=SQL(" AND ").join(conditions),
            text=text,
            name=name,
            limit=limit * SEARCH_CANDIDATE_FACTOR,
        ))
        candidate_ids = [row[0] for row in self.env.cr.fetchall()]
        allowed = set(self.env['product.product'].search(
            [('id', 'in', candidate_ids)] + self._quick_product_domain()
        ).ids)
        return [pid for pid in candidate_ids if pid in allowed][:limit]

    def _quick_top_seller_ids(self, limit):
        """Best sellers of the period across all customers (empty search)."""
        groups = self.env[self._quick_line_model]._read_group(
            self._quick_history_domain() + [
                ('product_id.active', '=', True),
                ('product_id.' + self._quick_product_ok_field, '=', True),
                ('product_id.type', '!=', 'combo'),
            ],
            ['product_id'], ['order_id:count_distinct'],
            order='order_id:count_distinct desc, product_id', limit=limit,
        )
        return [product.id for product, _count in groups]

    def quick_search_products(self, term, limit=None):
        self.ensure_one()
        limit = limit or self._quick_settings()['search_limit']
        qty, text = self._quick_parse_term(term)
        top_sellers = not text
        if top_sellers:
            product_ids = self._quick_top_seller_ids(limit)
        else:
            product_ids = self._quick_search_product_ids(text, limit)

        products = self.env['product.product'].browse(product_ids)
        prices = self._quick_pricelist_prices(products, qty)
        return {
            'qty': qty,
            'term': text,
            'top_sellers': top_sellers,
            'results': [{
                'product_id': product.id,
                'name': product.display_name,
                'default_code': product.default_code or '',
                'category': product.categ_id.display_name or '',
                'price': prices.get(product.id, 0.0),
                'uom': product.uom_id.name,
            } for product in products],
        }

    # ------------------------------------------------------------------
    # Adding lines
    # ------------------------------------------------------------------

    def quick_add_lines(self, lines):
        """Add ``[{product_id, qty, price_unit (optional)}]`` to the document.

        A product already on the document with the same unit price and unit of
        measure gets its quantity increased instead of a new line.
        """
        self.ensure_one()
        self._quick_check_editable()
        Line = self.env[self._quick_line_model]
        products = self.env['product.product'].search(
            [('id', 'in', [item.get('product_id') for item in lines])] + self._quick_product_domain()
        )
        added = []
        for item in lines:
            product = products.filtered(lambda p: p.id == item.get('product_id'))
            if not product:
                raise UserError(_("The selected product is not available for this document."))
            qty = item.get('qty')
            try:
                qty = 1.0 if qty is None else float(qty)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                raise UserError(_("The quantity must be greater than zero."))

            price = item.get('price_unit')
            expected = price if price is not None else self._quick_expected_price(product, qty)
            target = self._quick_mergeable_lines(product).filtered(
                lambda line: not self.currency_id.compare_amounts(line.price_unit, expected)
            )[:1]
            if target:
                target[self._quick_line_qty_field] += qty
            else:
                vals = {'order_id': self.id, 'product_id': product.id, self._quick_line_qty_field: qty}
                if price is not None:
                    vals['price_unit'] = price
                Line.create(vals)
            added.append({'product_id': product.id, 'name': product.display_name, 'qty': qty, 'merged': bool(target)})
        return {'added': added}
