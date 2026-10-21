{
    'name': 'Surtecnica - Remito desde el pedido de venta',
    'version': '17.0.1.18.1',
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
  se emite la factura del pedido, con el calendario laboral de la compañía. Los
  feriados no suman, siempre que estén cargados ahí: el día se resuelve por el
  mediodía local, así que un feriado cargado desde la pantalla de Odoo resta ese día
  y no también el siguiente, y al cargarlo o borrarlo los remitos con sello se
  vuelven a medir solos. El plazo contra el que se
  compara se carga en la ficha de la compañía y nace vacío: mientras tanto se miden
  los días pero no se marca a nadie como excedido. Los pedidos con varias entregas
  o varias facturas quedan como «No determinable» en vez de recibir un plazo que no
  se puede atribuir. Menú: Inventario > Operaciones > Plazo de facturación.
* Registra POR QUÉ un remito todavía no se facturó, con los cuatro casos que
  distingue la empresa: espera la HES, no lo retiraron, no se factura, u otro. El
  primero viene puesto del tilde; el resto lo marca quien factura. Sin ese dato el
  ranking de demoras mezcla atrasos con cosas que no lo son. Un remito marcado «no se
  factura» deja de acumular espera y sale de los promedios: no está esperando nada.
* Mide también la espera EN CURSO: los días hábiles que lleva un remito que todavía
  no se facturó. Hace falta junto al otro número, porque el promedio de los remitos
  facturados no ve al cliente que no factura nunca —sus remitos no tienen días que
  promediar— y entonces premia justamente al que más se cuelga. Un proceso diario lo
  refresca, porque depende de qué día es hoy.
* Avisa a quien factura cuando se confecciona un remito: le crea una actividad
  pendiente con vencimiento según el plazo, y la cierra sola cuando la factura se
  postea. El destinatario se elige en la ficha de la compañía y nace vacío: sin él
  no se avisa a nadie. El aviso es genérico: a los remitos que esperan HES también se
  les crea, y queda pendiente hasta que llegue el código.
* Valoriza lo entregado que todavia no se facturo y lo muestra por cliente. Es el
  saldo que hoy no esta en ninguna cuenta corriente: si la entrega no lleva
  comprobante no hay asiento, y el dato vive solo en el pedido. Se valoriza el
  remito renglon por renglon --cantidad entregada por el precio de su linea, con
  descuento y sin impuestos-- y no el pedido entero, porque un pedido con varias
  entregas se contaria una vez por cada remito. Van dos columnas de valor: la de la
  moneda del pedido, que no se totaliza porque hay pedidos en dolares y en pesos
  mezclados, y la convertida a la moneda de la compania al tipo de cambio del dia
  del remito, que es la que se suma. Un renglon sin linea de pedido detras no tiene
  precio de donde salir: no suma y marca el remito, en vez de estimarlo. Incluye
  los remitos marcados como "no se factura", que son justamente los que nunca van a
  tener comprobante. No registra nada: es lectura. Menu: Inventario > Operaciones >
  Entregado sin facturar.
* Trae una pantalla para cargar de corrido la lista de clientes que exigen HES, con
  la lista editable en línea y sin poder crear ni borrar contactos: marcarlos uno por
  uno desde su ficha eran tantas fichas como clientes. Menú: Inventario > Operaciones >
  Clientes que exigen HES, visible para quien tiene Facturación.
* Marca en cada remito si espera HES o autorización del cliente para poder
  facturarlo. El tilde nace marcado para los clientes que figuran en la lista de los
  que lo exigen —se carga en su ficha, cliente por cliente— y se destilda en el
  remito puntual que no la lleva. La decisión es del remito y no del cliente porque
  el mismo cliente la exige según el caso: un servicio sí y una entrega de rodillos
  no, o según el monto o si la compra es para una obra. A los remitos con el tilde
  marcado no se les reclama el plazo de facturación —el momento de facturar no
  depende de Sur Técnica— pero el aviso se les crea igual.

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
        'data/cron_dias_sin_facturar.xml',
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
