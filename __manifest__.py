{
    'name': 'Surtecnica - Remito desde el pedido de venta',
    'version': '17.0.1.11.0',
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
* Estampa la fecha en que se cargó el número del talonario. Es el hito con el que
  arranca el plazo de facturación: el remito quedó confeccionado. Se pone una sola
  vez —corregir un dígito después no la mueve— y se limpia si se borra el número.
* Mide el plazo de facturación: días hábiles entre que se confecciona el remito y
  se emite la factura del pedido, con el calendario laboral de la compañía (los
  feriados no suman, siempre que estén cargados ahí). El plazo contra el que se
  compara se carga en la ficha de la compañía y nace vacío: mientras tanto se miden
  los días pero no se marca a nadie como excedido. Los pedidos con varias entregas
  o varias facturas quedan como «No determinable» en vez de recibir un plazo que no
  se puede atribuir. Menú: Inventario > Operaciones > Plazo de facturación.
* Avisa a quien factura cuando se confecciona un remito: le crea una actividad
  pendiente con vencimiento según el plazo, y la cierra sola cuando la factura se
  postea. El destinatario se elige en la ficha de la compañía y nace vacío: sin él
  no se avisa a nadie. A los clientes con HES no se les avisa.
* Marca en la ficha del cliente si exige HES para facturar: el código de conformidad
  que algunos clientes emiten al recibir la mercadería y sin el cual rechazan la
  factura. A esos clientes no se les reclama el plazo de facturación, porque el
  momento de facturar no depende de Sur Técnica. Nace desmarcado y lo carga
  administración: no hay forma de deducirlo del sistema.

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
        'account',
        'resource',
        'mail',
    ],
    'data': [
        'security/remito_security.xml',
        'data/menu_restriccion.xml',
        'data/activity_type.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/stock_picking_views.xml',
        'views/indicador_views.xml',
        'report/remito_report.xml',
        'report/remito_template.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
