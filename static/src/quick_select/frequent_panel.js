import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { parseFloat } from "@web/views/fields/parsers";

// Widest frequency bar, in pixels, for the most purchased product.
const BAR_MAX_WIDTH = 60;

export class FrequentPanel extends Component {
    static template = "jaua_quick_product_select.FrequentPanel";
    static props = {
        record: Object,
        busy: Boolean,
        addLines: Function,
        repeatLastOrder: Function,
        formatAmount: Function,
        onUseSearch: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            products: [],
            lastOrder: false,
            pricePolicy: "last_price",
            qty: {},
        });
        onWillStart(() => this.load());
    }

    async load() {
        const { record } = this.props;
        const data = await this.orm.call(record.resModel, "quick_get_frequent_products", [[record.resId]]);
        this.state.products = data.products;
        this.state.lastOrder = data.last_order;
        this.state.pricePolicy = data.price_policy;
        this.state.qty = Object.fromEntries(data.products.map((p) => [p.product_id, "1"]));
        this.state.loading = false;
    }

    get maxTimes() {
        return Math.max(1, ...this.state.products.map((p) => p.times));
    }

    barWidth(product) {
        return Math.max(4, Math.round((product.times / this.maxTimes) * BAR_MAX_WIDTH));
    }

    timesLabel(product) {
        return product.times === 1 ? _t("1 order") : _t("%s orders", product.times);
    }

    relativeDate(value) {
        return value ? deserializeDateTime(value).toRelative() : "";
    }

    /** Secondary price shown under the main one when they differ. */
    secondaryPrice(product) {
        if (this.state.pricePolicy === "last_price") {
            return product.list_price !== product.price
                ? _t("list %s", this.props.formatAmount(product.list_price))
                : "";
        }
        return product.last_price && product.last_price !== product.price
            ? _t("last %s", this.props.formatAmount(product.last_price))
            : "";
    }

    readQty(productId) {
        try {
            const qty = parseFloat(String(this.state.qty[productId] || "1"));
            return qty > 0 ? qty : 0;
        } catch {
            return 0;
        }
    }

    async add(product) {
        const qty = this.readQty(product.product_id);
        if (!qty) {
            return;
        }
        const item = { product_id: product.product_id, qty };
        if (this.state.pricePolicy === "last_price" && product.last_date) {
            item.price_unit = product.price;
        }
        if (await this.props.addLines([item])) {
            this.state.qty[product.product_id] = "1";
        }
    }

    onQtyKeydown(ev, product) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.add(product);
        }
    }
}
