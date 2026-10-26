import { Component } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { quickSelectConfigs } from "./quick_select_config";
import { QuickSelectDialog } from "./quick_select_dialog";

// Alt+Q is already "Confirm" on quotations; Alt+E is free on the sale order form.
export const QUICK_SELECT_HOTKEY = "alt+e";

export class QuickSelectButton extends Component {
    static template = "jaua_quick_product_select.QuickSelectButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.dialog = useService("dialog");
        this.config = quickSelectConfigs[this.props.record.resModel];
        this.isOpen = false;
        useHotkey(QUICK_SELECT_HOTKEY, () => this.open(), { bypassEditableProtection: true });
    }

    get hotkeyLabel() {
        return "Alt+E";
    }

    get buttonTitle() {
        return _t("Quick selection (%s)", this.hotkeyLabel);
    }

    get isAvailable() {
        const { record, readonly } = this.props;
        return !readonly && this.config && this.config.editableStates.includes(record.data.state);
    }

    async open() {
        if (this.isOpen || !this.isAvailable) {
            return;
        }
        this.isOpen = true;
        try {
            // Lines are added server side, so the order must exist first.
            if (!(await this.props.record.save())) {
                this.isOpen = false;
                return;
            }
        } catch (error) {
            this.isOpen = false;
            throw error;
        }
        this.dialog.add(
            QuickSelectDialog,
            { record: this.props.record, config: this.config },
            { onClose: () => (this.isOpen = false) }
        );
    }
}

registry.category("view_widgets").add("quick_product_select", {
    component: QuickSelectButton,
});
