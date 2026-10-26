/**
 * Per-model settings of the quick selection dialog. A document type (e.g.
 * purchase.order in phase 2) only needs an entry here plus the Python mixin.
 */
export const quickSelectConfigs = {
    "sale.order": {
        linesField: "order_line",
        qtyField: "product_uom_qty",
        editableStates: ["draft", "sent"],
    },
};
