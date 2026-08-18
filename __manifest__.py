{
    'name': 'Surtecnica - Remito desde el pedido de venta',
    'version': '17.0.1.1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Imprime el remito con el formato del preimpreso, tomando los datos del pedido de venta',
    'description': """
Remito A4 que replica el formato que hoy sale de Flexxus, generado desde la
entrega que el pedido de venta ya crea en Odoo.

Por qué
-------
Sur Técnica entrega mercadería con un remito de talonario preimpreso (documento
código 91, con CAI) y le abrocha un impreso con el detalle de los ítems. Ese
impreso hoy se carga a mano en un sistema aparte, duplicando lo que el pedido de
venta de Odoo ya tiene cargado.

El obstáculo para imprimirlo directo desde Odoo era la descripción: en Sur Técnica
usan un producto genérico como percha y escriben el ítem real en la descripción de
la línea del pedido. El movimiento de stock no conserva ese texto — copia el
nombre del producto —, así que un remito armado sobre el albarán salía con todos
los renglones iguales. Medido sobre el pedido S05970: sus tres líneas
("Módulo 250mm", "Paletas lado izquierdo", "Paletas lado derecho") figuran las
tres como "BANDA MODULAR IC" en el albarán.

Qué hace
--------
* Agrega al albarán el número del remito preimpreso, que se carga a mano copiando
  el que trae el talonario de papel, y controla que no se repita dentro de la
  misma razón social.
* Agrega los campos del bloque de observaciones que hoy se escribe en el impreso:
  OC del cliente, bultos, flete, valor declarado y dirección de entrega.
* Imprime el remito A4 tomando la descripción de la línea del pedido de venta, no
  del producto.

Qué NO hace
-----------
No mueve inventario ni exige validar la entrega: el remito se imprime sobre el
albarán en cualquier estado. Validar sigue siendo una decisión del operador, para
cuando el inventario esté cargado. Tampoco cambia la política de facturación ni
toca los albaranes ya existentes: la descripción se resuelve en el impreso, no
reescribiendo datos.

Complementa surtecnica_firma_traslados: ese módulo habilita la firma digital sobre
el albarán validado; este imprime el bloque de recepción para firmar a mano.
    """,
    'author': 'Yagüven C.G.',
    'website': 'https://www.yaguven.com',
    'depends': [
        'stock',
        'sale_stock',
        'l10n_ar',
    ],
    'data': [
        'security/remito_security.xml',
        'data/menu_restriccion.xml',
        'views/stock_picking_views.xml',
        'report/remito_report.xml',
        'report/remito_template.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
