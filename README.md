# Selección rápida de productos (`jaua_quick_product_select`)

Acelera la captura de productos en las órdenes de venta de Odoo 18 Community.

- **Buscador de comandos**: escribe nombre, referencia o código de barras; la
  cantidad va al inicio (`3 rj45`, `3x rj45`, `2.5 cable`). Todas las palabras
  deben coincidir, en cualquier orden, sin importar acentos ni mayúsculas.
  `↑` `↓` para moverse, `Enter` agrega, `Esc` limpia (con el campo vacío
  cierra).
- **Categorías y cuadrícula con imágenes** (el "modelo C, botones por
  categoría" de la especificación, integrado en el buscador en lugar de una
  pestaña aparte): botones con las categorías de primer nivel (hijas directas
  de la raíz) que tienen productos vendibles; una sola activa a la vez, se
  desactiva al tocarla de nuevo. Con el campo vacío se muestra una cuadrícula
  con imagen: **Recientes** (últimos productos que agregó ese vendedor, modo
  inicial) o **Más vendidos** del periodo, ambos filtrados por la categoría
  activa. Cada imagen indica cuántas unidades lleva ya la orden. En el móvil el
  diálogo ocupa toda la pantalla y el resumen del pedido se pliega.
- **Frecuentes del cliente**: productos que más ha comprado la empresa del
  cliente (todos sus contactos comparten historial), por número de pedidos
  confirmados en el periodo configurado. "Repetir último pedido" agrega todas
  las líneas de su último pedido confirmado.

Se abre con el botón **Selección rápida** junto a las líneas del pedido o con
**Alt+E** (Alt+Q ya es "Confirmar" en el formulario de venta). Solo aparece en
borrador y cotización enviada, para el grupo *Ventas / Usuario: solo sus
documentos* y superiores. Si la orden no está guardada, se guarda antes de abrir.

Al agregar un producto que ya está en la orden con el mismo precio y unidad de
medida, se suma la cantidad en lugar de crear otra línea (nunca sobre líneas con
descuento manual ni anticipos).

## Configuración

*Ventas → Configuración → Ajustes → Selección rápida de productos*:

| Ajuste | Predeterminado |
|---|---|
| Periodo de historial (meses) | 12 |
| Precio en frecuentes: último precio pagado por el cliente / lista de precios | Último precio |
| Resultados del buscador | 8 |

## Instalación

La carpeta del módulo debe estar en la ruta de addons (`/mnt/jaua-addons`).
Instalar y probar primero en una base de datos de prueba.

Desde la interfaz: *Aplicaciones → Actualizar lista de aplicaciones*, buscar
"Selección rápida de productos" e instalar.

Desde la línea de comandos (en la carpeta del `docker-compose.yml`; `run` pasa
por el entrypoint de la imagen, que agrega los datos de conexión a la base):

```bash
# Instalar
docker compose run --rm web odoo -d <base> -i jaua_quick_product_select --stop-after-init
# Actualizar después de cambios
docker compose run --rm web odoo -d <base> -u jaua_quick_product_select --stop-after-init
# Ejecutar las pruebas
docker compose run --rm web odoo -d <base> -u jaua_quick_product_select \
    --test-enable --test-tags /jaua_quick_product_select --stop-after-init
```

Después de instalar o actualizar, reiniciar el contenedor `web` para que el
servidor en ejecución cargue el código nuevo.

Al instalarse crea la extensión `unaccent` de PostgreSQL, usada solo por este
módulo (no activa la opción global `unaccent` de Odoo). Si no se puede crear,
la búsqueda funciona pero distingue acentos.

## Diseño

- `models/quick_select_mixin.py`: lógica común (`quick.select.mixin`).
  `sale.order` la hereda y solo define campos y estados propios; Compras
  (fase 2) bastará con heredarla en `purchase.order` y agregar su entrada en
  `static/src/quick_select/quick_select_config.js`.
- Las líneas se crean en el servidor y el formulario se recarga: precio,
  impuestos, unidad de medida y posición fiscal salen del cálculo estándar de
  Odoo, y la fusión de líneas queda en un solo lugar probado.
- La búsqueda usa SQL solo para aplicar `unaccent` al nombre traducido; los
  candidatos pasan después por `search()`, así que se respetan permisos y
  reglas de registro. No se usa `sudo()` salvo para leer los tres ajustes del
  módulo (`ir.config_parameter` solo lo leen administradores).
- Estilos solo con variables SCSS de Odoo/Bootstrap (`$primary`,
  `$border-color`, `$o-view-background-color`…). El backend de Odoo 18 no
  define las variables CSS de Bootstrap (`--bs-*`), así que no deben usarse.
  Odoo Community no tiene modo oscuro en el backend (lo agrega `web_enterprise`);
  si existiera, recompila estas mismas variables con sus valores oscuros.
- Los productos combo no se ofrecen: sus componentes se arman en el formulario.
- "Recientes" sale de las líneas que creó el usuario (`create_uid`), sin tabla
  adicional; en empate de fecha (líneas de una misma operación) decide el id
  de línea más reciente.
