import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { highlightSegments } from "./highlight";

const SEARCH_DELAY = 200;
// Per-browser preference: keep the category buttons unfolded or not.
const SHOW_CATEGORIES_KEY = "jaua_quick_product_select.show_categories";

function readShowCategories() {
    try {
        return browser.localStorage.getItem(SHOW_CATEGORIES_KEY) === "1";
    } catch {
        return false;
    }
}

/**
 * Command search with first-level category filters. With text it lists the
 * matches; with an empty field it shows image tiles of the user's recent
 * products or the best sellers (the "buttons by category" model).
 */
export class SearchPanel extends Component {
    static template = "jaua_quick_product_select.SearchPanel";
    static props = {
        record: Object,
        busy: Boolean,
        addLines: Function,
        formatAmount: Function,
        formatQty: Function,
        orderQty: Object,
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
            mode: "recent",
            resultMode: "recent",
            categories: [],
            categoryId: false,
            showCategories: readShowCategories(),
            active: 0,
            loading: false,
        });
        this.requestId = 0;
        this.debouncedSearch = useDebounced(this.search, SEARCH_DELAY);
        onWillStart(() => Promise.all([this.loadCategories(), this.search()]));
    }

    async loadCategories() {
        const { record } = this.props;
        this.state.categories = await this.orm.call(record.resModel, "quick_get_categories", [[record.resId]]);
    }

    async search() {
        const requestId = ++this.requestId;
        const { record } = this.props;
        const input = this.state.term;
        this.state.loading = true;
        const data = await this.orm.call(record.resModel, "quick_search_products", [[record.resId], input], {
            category_id: this.state.categoryId || false,
            mode: this.state.mode,
        });
        // Ignore answers to searches typed over by a newer one.
        if (requestId !== this.requestId) {
            return;
        }
        Object.assign(this.state, {
            searchedInput: input,
            qty: data.qty,
            searchedTerm: data.term,
            results: data.results,
            resultMode: data.mode,
            active: 0,
            loading: false,
        });
    }

    searchNow() {
        this.debouncedSearch.cancel();
        return this.search();
    }

    get isGrid() {
        return this.state.resultMode !== "search";
    }

    get words() {
        return this.state.searchedTerm.split(/\s+/).filter(Boolean);
    }

    get qtyLabel() {
        return _t("%s units", this.props.formatQty(this.state.qty));
    }

    get emptyMessage() {
        if (this.state.resultMode === "search") {
            return _t('No product matches "%s". Try the internal reference.', this.state.searchedTerm);
        }
        if (this.state.resultMode === "recent") {
            return _t("You have not added products yet. Try the best sellers.");
        }
        return _t("No sales in the configured period yet. Type to search the catalog.");
    }

    segments(text) {
        return highlightSegments(text, this.words);
    }

    imageUrl(result) {
        const unique = encodeURIComponent(result.image_unique || "");
        return `/web/image/product.product/${result.product_id}/image_128?unique=${unique}`;
    }

    focusInput() {
        this.inputRef.el?.focus();
    }

    get activeCategory() {
        return this.state.categories.find((category) => category.id === this.state.categoryId);
    }

    toggleCategories() {
        this.state.showCategories = !this.state.showCategories;
        try {
            browser.localStorage.setItem(SHOW_CATEGORIES_KEY, this.state.showCategories ? "1" : "0");
        } catch {
            // Storage unavailable (private mode): the toggle still works for this dialog.
        }
    }

    selectCategory(categoryId) {
        // Single active filter: tapping the active one turns it off.
        this.state.categoryId = this.state.categoryId === categoryId ? false : categoryId;
        // Fold again unless the user chose to keep the buttons unfolded; the
        // active category stays visible as a tag next to the toggle.
        if (!readShowCategories()) {
            this.state.showCategories = false;
        }
        this.searchNow();
        this.focusInput();
    }

    setMode(mode) {
        if (this.state.mode !== mode) {
            this.state.mode = mode;
            this.searchNow();
        }
        this.focusInput();
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
        this.state.term = "";
        if (this.inputRef.el) {
            this.inputRef.el.value = "";
        }
        this.focusInput();
        this.searchNow();
    }

    async onKeydown(ev) {
        // Left/right move between tiles only while the field is empty, so
        // they keep moving the text cursor when typing.
        const gridMove = this.isGrid && !this.state.term;
        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                this.setActive(this.state.active + 1);
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.setActive(this.state.active - 1);
                break;
            case "ArrowRight":
                if (gridMove) {
                    ev.preventDefault();
                    this.setActive(this.state.active + 1);
                }
                break;
            case "ArrowLeft":
                if (gridMove) {
                    ev.preventDefault();
                    this.setActive(this.state.active - 1);
                }
                break;
            case "Enter":
                ev.preventDefault();
                // Make sure Enter acts on the results of what is typed now.
                if (this.state.searchedInput !== this.state.term) {
                    await this.searchNow();
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
