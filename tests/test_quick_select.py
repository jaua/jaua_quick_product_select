from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQuickSelect(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('jaua_quick_product_select.price_policy', 'last_price')
        cls.env['ir.config_parameter'].sudo().set_param('jaua_quick_product_select.history_months', '12')

        cls.company_partner = cls.env['res.partner'].create({'name': 'Clínica San Rafael', 'is_company': True})
        cls.contact_a = cls.env['res.partner'].create({'name': 'Ana', 'parent_id': cls.company_partner.id})
        cls.contact_b = cls.env['res.partner'].create({'name': 'Beto', 'parent_id': cls.company_partner.id})
        cls.other_customer = cls.env['res.partner'].create({'name': 'Despacho Ruiz', 'is_company': True})

        Product = cls.env['product.product']
        cls.camera = Product.create({'name': 'Cámara IP domo 4 MP', 'default_code': 'CAM-IP-4MP', 'list_price': 1180.0})
        cls.rj45 = Product.create({'name': 'Conectores RJ45 Cat6 (100 pzs)', 'default_code': 'RJ45-CAT6-100',
                                   'list_price': 420.0, 'barcode': '7501234567890'})
        cls.cable = Product.create({'name': 'Bobina cable UTP Cat6 305 m', 'default_code': 'CAB-CAT6-305', 'list_price': 2890.0})
        cls.not_for_sale = Product.create({'name': 'Cámara interna de prueba', 'default_code': 'CAM-INT', 'sale_ok': False})

    def _confirmed_order(self, partner, lines, months_ago=0):
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty, 'price_unit': price})
                           for product, qty, price in lines],
        })
        order.action_confirm()
        order.date_order = fields.Datetime.now() - relativedelta(months=months_ago)
        return order

    def _quotation(self, partner=None):
        return self.env['sale.order'].create({'partner_id': (partner or self.contact_a).id})

    # Frequent products ---------------------------------------------------

    def test_frequent_products_counts_orders_per_commercial_partner(self):
        self._confirmed_order(self.contact_a, [(self.camera, 2, 1150.0), (self.rj45, 1, 410.0)], months_ago=3)
        self._confirmed_order(self.contact_b, [(self.camera, 1, 1100.0)], months_ago=1)
        # Two lines of the same product in one order count as one order.
        self._confirmed_order(self.contact_a, [(self.camera, 1, 1120.0), (self.camera, 4, 1120.0)], months_ago=2)
        # Not counted: another customer, an unconfirmed quotation, outside the period.
        self._confirmed_order(self.other_customer, [(self.rj45, 5, 400.0)])
        self._quotation().write({'order_line': [(0, 0, {'product_id': self.rj45.id, 'product_uom_qty': 1})]})
        self._confirmed_order(self.contact_a, [(self.rj45, 1, 300.0)], months_ago=14)

        data = self._quotation(self.contact_b).quick_get_frequent_products()
        rows = {row['product_id']: row for row in data['products']}

        self.assertEqual([row['product_id'] for row in data['products']], [self.camera.id, self.rj45.id])
        self.assertEqual(rows[self.camera.id]['times'], 3)
        self.assertEqual(rows[self.rj45.id]['times'], 1)
        # Last price comes from the most recent order (1 month ago, contact B).
        self.assertEqual(rows[self.camera.id]['last_price'], 1100.0)
        self.assertEqual(rows[self.camera.id]['price'], 1100.0)
        self.assertEqual(rows[self.camera.id]['list_price'], 1180.0)
        self.assertTrue(data['last_order'])

    def test_frequent_products_pricelist_policy(self):
        self.env['ir.config_parameter'].sudo().set_param('jaua_quick_product_select.price_policy', 'pricelist')
        self._confirmed_order(self.contact_a, [(self.camera, 1, 999.0)])
        row = self._quotation().quick_get_frequent_products()['products'][0]
        self.assertEqual(row['last_price'], 999.0)
        self.assertEqual(row['price'], 1180.0)

    def test_frequent_products_without_history(self):
        data = self._quotation(self.other_customer).quick_get_frequent_products()
        self.assertEqual(data['products'], [])
        self.assertFalse(data['last_order'])

    # Command search ------------------------------------------------------

    def test_parse_quantity(self):
        parse = self.env['sale.order']._quick_parse_term
        self.assertEqual(parse('3 rj45'), (3.0, 'rj45'))
        self.assertEqual(parse('3x rj45'), (3.0, 'rj45'))
        self.assertEqual(parse('3 x rj45 cat6'), (3.0, 'rj45 cat6'))
        self.assertEqual(parse('2.5 cable'), (2.5, 'cable'))
        self.assertEqual(parse('2,5 cable'), (2.5, 'cable'))
        self.assertEqual(parse('rj45'), (1.0, 'rj45'))
        self.assertEqual(parse('880030081'), (1.0, '880030081'))
        self.assertEqual(parse('0 rj45'), (1.0, '0 rj45'))
        self.assertEqual(parse('  '), (1.0, ''))

    def test_search_all_words_any_order_case_and_accents(self):
        order = self._quotation()
        result = order.quick_search_products('3 DOMO camara')
        self.assertEqual(result['qty'], 3.0)
        self.assertEqual([r['product_id'] for r in result['results']], [self.camera.id])
        # Every word must match: "camara cat6" matches no single product.
        self.assertFalse(order.quick_search_products('camara cat6')['results'])
        # Products that cannot be sold are excluded.
        self.assertNotIn(self.not_for_sale.id, [r['product_id'] for r in order.quick_search_products('camara')['results']])

    def test_search_by_reference_and_barcode(self):
        order = self._quotation()
        self.assertEqual(order.quick_search_products('cab-cat6')['results'][0]['product_id'], self.cable.id)
        self.assertEqual(order.quick_search_products('7501234567890')['results'][0]['product_id'], self.rj45.id)

    def test_search_respects_limit_and_empty_term_returns_top_sellers(self):
        self._confirmed_order(self.other_customer, [(self.rj45, 1, 420.0)])
        self._confirmed_order(self.contact_a, [(self.rj45, 1, 420.0), (self.cable, 1, 2890.0)])
        order = self._quotation()
        self.assertEqual(len(order.quick_search_products('cat6', limit=1)['results']), 1)
        result = order.quick_search_products('', limit=1000)
        self.assertTrue(result['top_sellers'])
        ids = [r['product_id'] for r in result['results']]
        # Two orders for RJ45, one for the cable (demo data may add others).
        self.assertLess(ids.index(self.rj45.id), ids.index(self.cable.id))

    # Adding lines --------------------------------------------------------

    def test_add_lines_merges_same_product_and_price(self):
        order = self._quotation()
        order.quick_add_lines([{'product_id': self.rj45.id, 'qty': 2}])
        result = order.quick_add_lines([{'product_id': self.rj45.id, 'qty': 3}])
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 5)
        self.assertTrue(result['added'][0]['merged'])

        # A different price creates a separate line.
        order.quick_add_lines([{'product_id': self.rj45.id, 'qty': 1, 'price_unit': 399.0}])
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(sorted(order.order_line.mapped('price_unit')), [399.0, 420.0])

    def test_add_lines_uses_pricelist_price_and_taxes(self):
        order = self._quotation()
        order.quick_add_lines([{'product_id': self.camera.id, 'qty': 1}])
        line = order.order_line
        self.assertEqual(line.price_unit, 1180.0)
        self.assertEqual(line.tax_id, self.camera.taxes_id._filter_taxes_by_company(order.company_id))

    def test_add_lines_rejects_invalid_input(self):
        order = self._quotation()
        with self.assertRaises(UserError):
            order.quick_add_lines([{'product_id': self.rj45.id, 'qty': 0}])
        with self.assertRaises(UserError):
            order.quick_add_lines([{'product_id': self.not_for_sale.id, 'qty': 1}])

    def test_confirmed_order_is_locked(self):
        order = self._confirmed_order(self.contact_a, [(self.rj45, 1, 420.0)])
        with self.assertRaises(UserError):
            order.quick_add_lines([{'product_id': self.cable.id, 'qty': 1}])
        with self.assertRaises(UserError):
            order.quick_repeat_last_order()
        self.assertEqual(len(order.order_line), 1)

    # Repeat last order ---------------------------------------------------

    def test_repeat_last_order(self):
        self._confirmed_order(self.contact_a, [(self.camera, 5, 1000.0)], months_ago=2)
        self._confirmed_order(self.contact_b, [(self.camera, 2, 1150.0), (self.rj45, 3, 410.0)], months_ago=1)
        order = self._quotation()
        order.quick_add_lines([{'product_id': self.rj45.id, 'qty': 1, 'price_unit': 410.0}])

        result = order.quick_repeat_last_order()

        lines = {line.product_id: line for line in order.order_line}
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(lines[self.camera].product_uom_qty, 2)
        self.assertEqual(lines[self.camera].price_unit, 1150.0)
        # Same product and price as an existing line: quantity is added.
        self.assertEqual(lines[self.rj45].product_uom_qty, 4)
        self.assertTrue(result['source_order'])

    def test_repeat_last_order_without_history(self):
        with self.assertRaises(UserError):
            self._quotation(self.other_customer).quick_repeat_last_order()
