import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { highlightSegments } from "./highlight";

const SEARCH_DELAY = 200;

export class SearchPanel extends Component {
    static template = "jaua_quick_product_select.SearchPanel";
    static props = {
        record: Object,
        busy: Boolean,
        addLines: Function,
        formatAmount: Function,
        formatQty: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.inputRef = useRef("input");
        useAutofocus({ refName: "input" });
        this.state = useState({
            term: "",
            // Raw input the current results answer, quantity prefix included.
            searchedInput: null,
            qty: 1,
            searchedTerm: "",
            results: [],
            topSellers: true,
            active: 0,
            loading: false,
        });
        this.requestId = 0;
        this.debouncedSearch = useDebounced(this.search, SEARCH_DELAY);
        onWillStart(() => this.search());
    }

    async search() {
        const requestId = ++this.requestId;
        const { record } = this.props;
        const input = this.state.term;
        this.state.loading = true;
        const data = await this.orm.call(record.resModel, "quick_search_products", [
            [record.resId],
            input,
        ]);
        // Ignore answers to searches typed over by a newer one.
        if (requestId !== this.requestId) {
            return;
        }
        Object.assign(this.state, {
            searchedInput: input,
            qty: data.qty,
            searchedTerm: data.term,
            results: data.results,
            topSellers: data.top_sellers,
            active: 0,
            loading: false,
        });
    }

    get words() {
        return this.state.searchedTerm.split(/\s+/).filter(Boolean);
    }

    get qtyLabel() {
        return _t("%s units", this.props.formatQty(this.state.qty));
    }

    segments(text) {
        return highlightSegments(text, this.words);
    }

    onInput(ev) {
        this.state.term = ev.target.value;
        this.debouncedSearch();
    }

    setActive(index) {
        const count = this.state.results.length;
        if (count) {
            this.state.active = (index + count) % count;
        }
    }

    async add(result) {
        if (!result || this.props.busy) {
            return;
        }
        const added = await this.props.addLines([{ product_id: result.product_id, qty: this.state.qty }]);
        if (added) {
            this.clear();
        }
    }

    clear() {
        this.debouncedSearch.cancel();
        this.state.term = "";
        if (this.inputRef.el) {
            this.inputRef.el.value = "";
            this.inputRef.el.focus();
        }
        this.search();
    }

    async onKeydown(ev) {
        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                this.setActive(this.state.active + 1);
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.setActive(this.state.active - 1);
                break;
            case "Enter":
                ev.preventDefault();
                // Make sure Enter acts on the results of what is typed now.
                if (this.state.searchedInput !== this.state.term) {
                    this.debouncedSearch.cancel();
                    await this.search();
                }
                await this.add(this.state.results[this.state.active]);
                break;
            case "Escape":
                // With text, Escape only clears it; when empty it closes the dialog.
                if (this.state.term) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    this.clear();
                }
                break;
        }
    }
}
