from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Si el calendario de la compañía no dice nada, se asume lunes a viernes. No es una
# suposición sobre Sur Técnica: es el default de Odoo para una semana laboral.
DIAS_LABORABLES_POR_DEFECTO = {0, 1, 2, 3, 4}
# Tope defensivo del recorrido día por día: un remito de 2015 sin facturar no debe
# dejar el compute iterando miles de vueltas.
TOPE_DIAS = 2000


class StockPicking(models.Model):
    _inherit = "stock.picking"

    guvens_remito_number = fields.Char(
        string="Nº de remito preimpreso",
        copy=False,
        tracking=True,
        help="Número que ya viene impreso en el talonario de papel, con el formato "
             "0002-00010576. Se carga a mano: el impreso de Odoo se abrocha a ese "
             "talonario, así que tiene que llevar el mismo número.",
    )

    guvens_remito_fecha = fields.Datetime(
        string="Remito confeccionado el",
        readonly=True,
        copy=False,
        help="Momento en que se cargó el número del talonario. Lo pone el sistema "
             "solo y es el que arranca el reloj del plazo de facturación.\n\n"
             "Se estampa una sola vez: corregir un dígito del número después no lo "
             "mueve, porque el remito se confeccionó cuando se confeccionó. Si en "
             "cambio se borra el número, la fecha se limpia.",
    )

    # --- indicador de plazo de facturación ---
    guvens_factura_id = fields.Many2one(
        "account.move",
        string="Factura del remito",
        compute="_compute_guvens_plazo",
        store=True,
        help="Primera factura de cliente posteada del pedido al que pertenece este "
             "remito. Si el pedido tiene varias entregas o varias facturas, queda "
             "vacío: ahí no se puede saber qué factura corresponde a qué remito.",
    )
    guvens_dias_a_factura = fields.Integer(
        string="Días hábiles hasta la factura",
        compute="_compute_guvens_plazo",
        store=True,
        help="Días hábiles entre el día en que se confeccionó el remito y el día en "
             "que se emitió la factura, según el calendario laboral de la compañía. "
             "El día del remito no cuenta: un remito del viernes facturado el lunes "
             "lleva un día.",
    )
    guvens_plazo_estado = fields.Selection(
        selection=[
            ("en_plazo", "Dentro del plazo"),
            ("excedido", "Excedido"),
            ("facturado", "Facturado (sin plazo definido)"),
            ("hes", "Cliente con HES"),
            ("pendiente", "Pendiente de facturar"),
            ("previo", "Facturada antes del remito"),
            ("indeterminado", "No determinable"),
        ],
        string="Plazo de facturación",
        compute="_compute_guvens_plazo",
        store=True,
        help="Estado del remito frente al plazo de facturación.\n\n"
             "«Cliente con HES» son los que emiten un código de conformidad al recibir: "
             "se les miden los días igual, para poder compararlos, pero no se les "
             "reclama el plazo porque facturar no depende de nosotros.\n\n"
             "«No determinable» es un pedido con varias entregas o varias facturas, "
             "donde no se puede atribuir una factura a un remito sin revisarlo a mano.\n\n"
             "«Facturado (sin plazo definido)» aparece mientras no se cargue el plazo "
             "en la ficha de la compañía.",
    )

    # --- bloque de observaciones que hoy se escribe en el impreso ---
    guvens_remito_oc = fields.Char(
        string="OC del cliente",
        help="Orden de compra con la que el cliente pidió la mercadería.",
    )
    guvens_remito_bultos = fields.Char(string="Bultos")
    guvens_remito_flete = fields.Char(string="Flete")
    guvens_remito_valor_declarado = fields.Char(
        string="Valor declarado",
        help="Texto libre a propósito: el valor declarado suele expresarse en pesos "
             "aunque el pedido esté en dólares, así que no se ata a la moneda del pedido.",
    )
    guvens_remito_direccion_entrega = fields.Char(string="Dirección de entrega")
    guvens_remito_observaciones = fields.Text(string="Otras observaciones")

    guvens_remito_imprime_precios = fields.Boolean(
        string="Imprimir precios en el remito",
        default=True,
        help="Desmarcar cuando el remito acompaña mercadería sin valorizar.",
    )

    # ------------------------------------------------------------------
    #  Indicador de plazo
    # ------------------------------------------------------------------
    def _guvens_feriados(self, calendario, desde, hasta):
        """Fechas no laborables cargadas en el calendario, como conjunto de dates.

        Hoy el calendario de Sur Técnica no tiene ninguna cargada, así que los
        feriados cuentan como hábiles. No se precargan por código: cambian cada año
        y por decreto, y Odoo ya tiene la pantalla donde se cargan. En cuanto
        alguien las cargue ahí, este cálculo las toma solo.
        """
        if not calendario:
            return set()
        ausencias = self.env["resource.calendar.leaves"].search([
            ("calendar_id", "in", [calendario.id, False]),
            ("resource_id", "=", False),
            ("date_from", "<=", fields.Datetime.to_string(
                fields.Datetime.to_datetime(hasta) + timedelta(days=1))),
            ("date_to", ">=", fields.Datetime.to_string(fields.Datetime.to_datetime(desde))),
        ])
        fechas = set()
        for ausencia in ausencias:
            dia = ausencia.date_from.date()
            fin = ausencia.date_to.date()
            while dia <= fin and dia <= hasta:
                fechas.add(dia)
                dia += timedelta(days=1)
        return fechas

    def _guvens_tz(self):
        """Zona en la que se cuentan los días. La del calendario de la compañía."""
        calendario = self.company_id.resource_calendar_id
        return pytz.timezone(
            (calendario and calendario.tz)
            or self.env.user.tz
            or "America/Argentina/Buenos_Aires"
        )

    def _guvens_fecha_local(self, momento_utc):
        """Día del calendario local que corresponde a un Datetime de Odoo.

        No es un detalle: los Datetime de Odoo son UTC, y un remito cargado un
        viernes a las 22:30 de acá figura como sábado en UTC. Sin convertir, ese
        remito arrancaría el reloj el fin de semana.
        """
        self.ensure_one()
        return pytz.UTC.localize(momento_utc).astimezone(self._guvens_tz()).date()

    def _guvens_dias_habiles(self, desde, hasta):
        """Días hábiles entre dos FECHAS locales (no datetimes: días del calendario).

        El día del remito no cuenta; el de la factura sí. Es como lo dijo Franco:
        remito el viernes, con hábiles vence el martes.
        """
        self.ensure_one()
        calendario = self.company_id.resource_calendar_id
        if hasta <= desde:
            return 0

        laborables = {int(a.dayofweek) for a in calendario.attendance_ids} \
            if calendario and calendario.attendance_ids else DIAS_LABORABLES_POR_DEFECTO
        feriados = self._guvens_feriados(calendario, desde, hasta)

        dias, dia, vueltas = 0, desde, 0
        while dia < hasta and vueltas < TOPE_DIAS:
            dia += timedelta(days=1)
            vueltas += 1
            if dia.weekday() in laborables and dia not in feriados:
                dias += 1
        return dias

    def _guvens_factura_del_remito(self):
        """La factura que corresponde a este remito, o False si no se puede saber.

        El apareo es por el pedido de venta. Cuando el pedido tiene varias entregas
        confeccionadas o varias facturas posteadas, devuelve False a propósito: en
        el informe del 20/10 eran 30 casos de 169, y atribuirles un plazo sería
        inventar cuál factura cubre cuál entrega.
        """
        self.ensure_one()
        pedido = self.sale_id
        if not pedido:
            return False
        facturas = pedido.invoice_ids.filtered(
            lambda m: m.move_type == "out_invoice" and m.state == "posted"
        )
        if len(facturas) != 1:
            return False
        remitos = pedido.picking_ids.filtered(lambda p: p.guvens_remito_number)
        if len(remitos) > 1:
            return False
        return facturas

    @api.depends(
        "guvens_remito_fecha",
        "sale_id",
        "sale_id.invoice_ids.state",
        "sale_id.invoice_ids.move_type",
        "sale_id.picking_ids.guvens_remito_number",
        "partner_id.guvens_requiere_hes",
    )
    def _compute_guvens_plazo(self):
        for picking in self:
            picking.guvens_factura_id = False
            picking.guvens_dias_a_factura = 0
            if not picking.guvens_remito_fecha:
                picking.guvens_plazo_estado = False
                continue

            factura = picking._guvens_factura_del_remito()
            if not factura:
                # Sin pedido o con el apareo ambiguo. Se distingue para no mezclar
                # "todavía no se facturó" con "no se puede saber".
                pedido = picking.sale_id
                hay_posteadas = pedido and pedido.invoice_ids.filtered(
                    lambda m: m.move_type == "out_invoice" and m.state == "posted")
                picking.guvens_plazo_estado = "indeterminado" if hay_posteadas else "pendiente"
                continue

            picking.guvens_factura_id = factura

            # Las dos puntas tienen que ser días LOCALES, y cada una viene de una
            # fuente distinta: el sello es un Datetime UTC y hay que convertirlo;
            # `invoice_date` ya es la fecha contable, sin hora ni zona. Tratar a la
            # segunda como si fuera UTC la corría un día hacia atrás.
            dia_remito = picking._guvens_fecha_local(picking.guvens_remito_fecha)
            dia_factura = factura.invoice_date or picking._guvens_fecha_local(
                factura.create_date)

            if dia_factura < dia_remito:
                # Facturaron y después entregaron. No es un atraso: es otro circuito.
                picking.guvens_plazo_estado = "previo"
                continue

            dias = picking._guvens_dias_habiles(dia_remito, dia_factura)
            picking.guvens_dias_a_factura = dias

            if picking.partner_id.guvens_requiere_hes:
                # Se le miden los días igual —Franco quiere comparar los dos grupos—
                # pero no se le reclama el plazo: facturar no depende de nosotros.
                picking.guvens_plazo_estado = "hes"
                continue

            plazo = picking.company_id.guvens_plazo_facturacion_dias
            if not plazo:
                picking.guvens_plazo_estado = "facturado"
            else:
                picking.guvens_plazo_estado = "en_plazo" if dias <= plazo else "excedido"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("guvens_remito_number"):
                vals["guvens_remito_number"] = vals["guvens_remito_number"].strip()
                vals.setdefault("guvens_remito_fecha", fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        """Estampa el sello de confección cuando aparece el número del talonario.

        El sello va DESPUÉS del super() y registro por registro, no dentro de `vals`:
        un mismo write puede alcanzar varios albaranes, unos con fecha y otros sin
        ella, y meterlo en `vals` se la pisaría a los que ya la tenían —que es
        justamente el dato que no se puede recuperar—.
        """
        if vals.get("guvens_remito_number"):
            vals["guvens_remito_number"] = vals["guvens_remito_number"].strip()
        elif "guvens_remito_number" in vals:
            # Le borraron el número: el remito dejó de estar confeccionado.
            vals["guvens_remito_fecha"] = False

        resultado = super().write(vals)

        if vals.get("guvens_remito_number"):
            sin_sello = self.filtered(lambda p: not p.guvens_remito_fecha)
            if sin_sello:
                super(StockPicking, sin_sello).write({
                    "guvens_remito_fecha": fields.Datetime.now(),
                })
        return resultado

    @api.constrains("guvens_remito_number", "company_id")
    def _check_guvens_remito_number(self):
        """Un número de preimpreso no puede repetirse dentro de la misma razón social.

        Cada talonario pertenece a una compañía y el número es su identidad frente a
        ARCA; repetirlo significa que dos entregas distintas dicen ser el mismo
        comprobante. Entre compañías sí puede coincidir: son talonarios distintos.
        """
        for picking in self:
            numero = picking.guvens_remito_number
            if not numero:
                continue
            repetido = self.sudo().search_count([
                ("id", "!=", picking.id),
                ("company_id", "=", picking.company_id.id),
                ("guvens_remito_number", "=", numero),
            ])
            if repetido:
                raise ValidationError(_(
                    "El remito preimpreso %(numero)s ya está cargado en otro albarán de "
                    "%(compania)s. Revisá el número del talonario.",
                    numero=numero,
                    compania=picking.company_id.display_name,
                ))


class StockMove(models.Model):
    _inherit = "stock.move"

    def _guvens_remito_descripcion(self):
        """Descripción que se imprime en el renglón del remito.

        En Sur Técnica cargan un producto genérico como percha y escriben el ítem real
        en la descripción de la línea del pedido. `description_picking` copia el nombre
        del producto, de modo que renglones distintos salen idénticos: en el pedido
        S05970 las tres líneas figuran como "BANDA MODULAR IC" en el albarán. Por eso
        la descripción se busca primero en la línea de venta.
        """
        self.ensure_one()
        descripcion = (
            self.sale_line_id.name
            or self.description_picking
            or self.product_id.display_name
        )
        return (descripcion or "").strip()

    def _guvens_remito_cantidad(self):
        """Cantidad a remitir.

        Toma la cantidad que el operador cargó como hecha y, si todavía no cargó nada,
        la pedida. Es lo que permite el remito parcial sin validar el albarán: se edita
        la cantidad hecha, se imprime, y el albarán queda abierto por el resto.
        """
        self.ensure_one()
        return self.quantity or self.product_uom_qty

    def _guvens_remito_precio_unitario(self):
        """Precio unitario del pedido, ya neto del descuento de la línea, para que el
        importe del remito cierre contra el pedido y contra la factura."""
        self.ensure_one()
        linea = self.sale_line_id
        if not linea:
            return 0.0
        return linea.price_unit * (1 - (linea.discount or 0.0) / 100.0)

    def _guvens_remito_importe(self):
        self.ensure_one()
        return self._guvens_remito_cantidad() * self._guvens_remito_precio_unitario()

    def _guvens_remito_moneda(self):
        self.ensure_one()
        return self.sale_line_id.currency_id or self.company_id.currency_id
