{
    'name': 'Selección rápida de productos',
    'version': '18.0.1.1.1',
    'summary': 'Captura rápida de productos en órdenes de venta: frecuentes del cliente y buscador de comandos',
    'author': 'JAUA SyTI',
    'website': 'https://app.jauamx.com',
    'category': 'Sales/Sales',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'jaua_quick_product_select/static/src/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
