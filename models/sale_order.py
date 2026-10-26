from odoo import fields, models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'quick.select.mixin']

    _quick_line_model = 'sale.order.line'
    _quick_line_qty_field = 'product_uom_qty'
    _quick_line_uom_field = 'product_uom'
    _quick_product_ok_field = 'sale_ok'
    _quick_confirmed_states = ('sale',)
    _quick_editable_states = ('draft', 'sent')

    def _quick_line_base_domain(self):
        return super()._quick_line_base_domain() + [('is_downpayment', '=', False)]

    def _quick_mergeable_lines(self, product):
        return super()._quick_mergeable_lines(product).filtered(
            lambda line: not line.is_downpayment and not line.discount and not line.combo_item_id
        )

    def _quick_pricelist_prices(self, products, qty):
        if not products:
            return {}
        date = self.date_order or fields.Datetime.now()
        if self.pricelist_id:
            return self.pricelist_id._get_products_price(
                products, qty, currency=self.currency_id, date=date,
            )
        return {
            product.id: product.currency_id._convert(product.lst_price, self.currency_id, self.company_id, date)
            for product in products
        }

    def _quick_expected_price(self, product, qty):
        # Same computation Odoo does for a new line (pricelist, taxes included
        # in price, fiscal position), without saving anything.
        line = self.env['sale.order.line'].new({
            'order_id': self.id,
            'product_id': product.id,
            'product_uom_qty': qty,
        })
        return line.price_unit
