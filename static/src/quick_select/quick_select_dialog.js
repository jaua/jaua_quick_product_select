import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";
import { formatMonetary } from "@web/views/fields/formatters";
import { FrequentPanel } from "./frequent_panel";
import { SearchPanel } from "./search_panel";

export class QuickSelectDialog extends Component {
    static template = "jaua_quick_product_select.QuickSelectDialog";
    static components = { Dialog, FrequentPanel, SearchPanel };
    static props = {
        record: Object,
        config: Object,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            tab: "search",
            busy: false,
            // On phones the order summary starts folded to leave room for products.
            showOrder: !this.env.isSmall,
            lastProductIds: [],
        });
    }

    get tabs() {
        return [
            {
                id: "search",
                title: _t("Command search"),
                subtitle: _t("For keyboard entry"),
            },
            {
                id: "frequent",
                title: _t("Frequent products"),
                subtitle: _t("For recurring orders"),
            },
        ];
    }

    get record() {
        return this.props.record;
    }

    get currencyId() {
        return this.record.data.currency_id && this.record.data.currency_id[0];
    }

    get orderLines() {
        const { linesField, qtyField } = this.props.config;
        return this.record.data[linesField].records
            .filter((line) => !line.data.display_type && line.data.product_id)
            .map((line) => ({
                id: line.id,
                productId: line.data.product_id[0],
                name: line.data.product_id[1],
                qty: line.data[qtyField],
                subtotal: line.data.price_subtotal,
            }));
    }

    /**
     * Untaxed / tax / total of the document. The sale order form does not
     * load amount_untaxed / amount_tax / amount_total (only list views do):
     * it shows the ``tax_totals`` summary, which is read here. Documents
     * without it fall back to the sum of their lines.
     */
    get totals() {
        const summary = this.record.data.tax_totals;
        if (summary && typeof summary === "object" && "total_amount_currency" in summary) {
            return {
                untaxed: summary.base_amount_currency,
                tax: summary.tax_amount_currency,
                total: summary.total_amount_currency,
            };
        }
        const lines = this.record.data[this.props.config.linesField].records;
        const untaxed = lines.reduce((sum, line) => sum + (line.data.price_subtotal || 0), 0);
        const total = lines.reduce((sum, line) => sum + (line.data.price_total || 0), 0);
        return { untaxed, tax: total - untaxed, total };
    }

    /** Quantity of each product already on the order, for the tile badges. */
    get orderQty() {
        const qty = {};
        for (const line of this.orderLines) {
            qty[line.productId] = (qty[line.productId] || 0) + line.qty;
        }
        return qty;
    }

    get productCount() {
        return this.orderLines.reduce((total, line) => total + line.qty, 0);
    }

    formatAmount(value) {
        return formatMonetary(value, { currencyId: this.currencyId });
    }

    formatQty(value) {
        return formatFloat(value, { trailingZeros: false });
    }

    /**
     * Add ``[{product_id, qty, price_unit?}]`` on the server, then reload the
     * form so the order lines, taxes and totals shown are Odoo's own.
     */
    async addLines(items) {
        return this.runOnOrder("quick_add_lines", [items]);
    }

    async repeatLastOrder() {
        const result = await this.runOnOrder("quick_repeat_last_order", []);
        if (result) {
            this.notification.add(_t("Last order %s added", result.source_order), { type: "success" });
        }
        return result;
    }

    async runOnOrder(method, args) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            if (!(await this.record.save())) {
                return false;
            }
            const result = await this.orm.call(this.record.resModel, method, [[this.record.resId], ...args]);
            await this.record.load();
            this.state.lastProductIds = result.added.map((item) => item.product_id);
            if (method === "quick_add_lines") {
                for (const item of result.added) {
                    this.notification.add(
                        _t("Added: %(qty)s × %(product)s", {
                            qty: this.formatQty(item.qty),
                            product: item.name,
                        }),
                        { type: "success" }
                    );
                }
            }
            return result;
        } finally {
            this.state.busy = false;
        }
    }
}
