from datetime import datetime, time, timedelta

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

    guvens_remito_requiere_hes = fields.Boolean(
        string="Requiere HES / autorización",
        compute="_compute_guvens_remito_requiere_hes",
        store=True,
        readonly=False,
        copy=False,
        tracking=True,
        help="Este remito necesita el código de conformidad del cliente (HES) o una "
             "autorización suya antes de poder facturarlo.\n\n"
             "Nace marcado si el cliente está en la lista de los que lo exigen, y se "
             "DESTILDA cuando esa entrega puntual no lo lleva. El mismo cliente puede "
             "exigirlo para un servicio y no para una entrega de mercadería, así que la "
             "decisión es de cada remito: la lista del cliente sólo da el valor inicial.\n\n"
             "Mientras esté marcado, al remito no se le reclama el plazo de facturación "
             "—el momento de facturar no depende de Sur Técnica— pero el aviso para "
             "facturar se crea igual y queda pendiente hasta que llegue el código.",
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
        # El agregado lo decide el modelo, no la vista: un `avg=""` en el XML sólo
        # cambia la etiqueta, mientras el read_group del servidor sigue devolviendo
        # la suma (medido el 20/10: el grupo "Excedido" mostraba 301 días). Y sumar
        # días de distintos remitos no significa nada; el promedio sí.
        group_operator="avg",
        help="Días hábiles entre el día en que se confeccionó el remito y el día en "
             "que se emitió la factura, según el calendario laboral de la compañía. "
             "El día del remito no cuenta: un remito del viernes facturado el lunes "
             "lleva un día.",
    )
    guvens_motivo_no_facturado = fields.Selection(
        selection=[
            ("espera_hes", "Espera HES / autorización"),
            ("no_retiro", "No lo retiraron todavía"),
            ("sin_factura", "No se factura"),
            ("otro", "Otro motivo"),
        ],
        string="Motivo de que no esté facturado",
        compute="_compute_guvens_motivo_no_facturado",
        store=True,
        readonly=False,
        copy=False,
        tracking=True,
        help="Por qué este remito todavía no tiene factura. Son los cuatro casos que "
             "distingue la empresa:\n\n"
             "• «Espera HES / autorización»: viene puesto solo cuando el remito tiene "
             "el tilde. No hay que cargarlo a mano.\n"
             "• «No lo retiraron todavía»: el transporte o el cliente no pasaron a "
             "buscar la mercadería. El remito está hecho pero la entrega no ocurrió.\n"
             "• «No se factura»: la entrega no lleva comprobante. Deja de acumular "
             "espera y sale de los promedios, porque no está esperando nada.\n"
             "• «Otro motivo»: cualquier otra razón; conviene dejarla escrita en las "
             "observaciones del remito.\n\n"
             "Sin este dato el ranking de demoras mezcla atrasos con cosas que no lo "
             "son: medido el 21/10/2026, los dos primeros puestos eran un remito que "
             "el cliente nunca retiró y uno que no se factura.",
    )

    guvens_dias_sin_facturar = fields.Integer(
        string="Días hábiles sin facturar",
        compute="_compute_guvens_dias_sin_facturar",
        store=True,
        group_operator="avg",
        help="Días hábiles que lleva esperando un remito que TODAVÍA no se facturó, "
             "contados hasta hoy. En los que ya tienen factura queda en cero: para "
             "esos el número es «Días hábiles hasta la factura».\n\n"
             "Las dos medidas hacen falta juntas. El promedio de los facturados no ve "
             "al cliente que no factura nunca —sus remitos no tienen días que "
             "promediar—, así que medir sólo eso premia justamente al que más se "
             "cuelga. Medido en testing el 21/10/2026: el cliente que más demora "
             "según la empresa tenía 7 remitos y los 7 sin facturar, o sea que no "
             "aparecía en ningún promedio.\n\n"
             "Lo recalcula un proceso diario, porque el número depende de qué día es "
             "hoy.",
    )
    guvens_plazo_estado = fields.Selection(
        selection=[
            ("en_plazo", "Dentro del plazo"),
            ("excedido", "Excedido"),
            ("facturado", "Facturado (sin plazo definido)"),
            ("hes", "Espera HES / autorización"),
            ("no_factura", "No se factura"),
            ("pendiente", "Pendiente de facturar"),
            ("previo", "Facturada antes del remito"),
            ("indeterminado", "No determinable"),
        ],
        string="Plazo de facturación",
        compute="_compute_guvens_plazo",
        store=True,
        help="Estado del remito frente al plazo de facturación.\n\n"
             "«Espera HES / autorización» son los remitos con ese tilde marcado: el "
             "cliente emite un código de conformidad al recibir, o tiene que autorizar. "
             "Se les miden los días igual, para poder compararlos, pero no se les "
             "reclama el plazo porque facturar no depende de nosotros.\n\n"
             "«No se factura» son los que alguien marcó con ese motivo: no están "
             "esperando nada, así que no acumulan espera ni entran en los promedios.\n\n"
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

    @api.depends("partner_id")
    def _compute_guvens_remito_requiere_hes(self):
        """Arranca del cliente, y después manda el remito.

        Es un compute EDITABLE (`readonly=False`): la lista de clientes que exigen HES
        da el valor con el que nace el remito, pero el operador lo destilda cuando esa
        entrega puntual no la lleva. Franco lo pidió así —«que de forma predeterminada
        figure con hes o autorización» y «que se pueda destildar cuando surja alguna
        excepción»—, porque las excepciones no se pueden saber de antemano: el mismo
        cliente la exige por servicio y no por mercadería, o según el monto o si la
        compra es para una obra.

        Depende sólo de `partner_id` y no del campo del cliente, para que marcar a un
        cliente en la lista no vuelva a pisar el tilde de los remitos ya confeccionados
        —y con él la decisión que alguien tomó a mano—. Si en cambio se cambia el
        cliente del albarán, el tilde se recalcula: cambió el hecho del que salía.
        """
        for picking in self:
            picking.guvens_remito_requiere_hes = picking.partner_id.guvens_requiere_hes

    # ------------------------------------------------------------------
    #  Indicador de plazo
    # ------------------------------------------------------------------
    def _guvens_feriados(self, calendario, desde, hasta):
        """Fechas no laborables cargadas en el calendario, como conjunto de dates.

        No se precargan por código: cambian cada año y por decreto, y Odoo ya tiene
        la pantalla donde se cargan. En cuanto alguien las cargue ahí, este cálculo
        las toma solo.

        El día se decide por el MEDIODÍA LOCAL, no por la fecha del Datetime en UTC.
        Es lo que hace la diferencia entre contar bien y restar un día de más: cuando
        alguien carga el feriado por la pantalla de Odoo, pone «09/11 00:00 a 09/11
        23:59» en hora de acá, y eso se guarda como 09/11 03:00 → 10/11 02:59 UTC.
        Leer la fecha de esos dos extremos da los días 9 **y 10**, así que el 10
        dejaba de contar sin que nadie lo hubiera marcado. Medido en testing el
        21/10/2026: un feriado de prueba el martes 13/10 bajó un remito de 4 días
        hábiles a 2.

        Con el mediodía, el único día que cae dentro del intervalo es el 9 — y
        también funciona al revés, para un feriado cargado por script de 00:00 a
        23:59 UTC, donde el extremo inferior cae en el día local anterior.
        """
        if not calendario:
            return set()
        ausencias = self.env["resource.calendar.leaves"].search([
            ("calendar_id", "in", [calendario.id, False]),
            ("resource_id", "=", False),
            ("date_from", "<=", fields.Datetime.to_string(
                fields.Datetime.to_datetime(hasta) + timedelta(days=1))),
            ("date_to", ">=", fields.Datetime.to_string(
                fields.Datetime.to_datetime(desde) - timedelta(days=1))),
        ])
        if not ausencias:
            return set()
        zona = self._guvens_tz()
        fechas = set()
        for ausencia in ausencias:
            primero = max(self._guvens_fecha_local(ausencia.date_from), desde)
            ultimo = min(self._guvens_fecha_local(ausencia.date_to), hasta)
            dia = primero
            while dia <= ultimo:
                mediodia = zona.localize(
                    datetime.combine(dia, time(12, 0))
                ).astimezone(pytz.UTC).replace(tzinfo=None)
                if ausencia.date_from <= mediodia <= ausencia.date_to:
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

    def _guvens_sumar_habiles(self, desde, cantidad):
        """La fecha que resulta de sumarle `cantidad` días hábiles a `desde`.

        Es el inverso de `_guvens_dias_habiles`, y usa el mismo calendario: si el
        vencimiento se calculara con días corridos, el aviso de un remito del
        viernes vencería el domingo.
        """
        self.ensure_one()
        calendario = self.company_id.resource_calendar_id
        laborables = {int(a.dayofweek) for a in calendario.attendance_ids} \
            if calendario and calendario.attendance_ids else DIAS_LABORABLES_POR_DEFECTO
        tope = desde + timedelta(days=TOPE_DIAS)
        feriados = self._guvens_feriados(calendario, desde, tope)
        dia, puestos, vueltas = desde, 0, 0
        while puestos < cantidad and vueltas < TOPE_DIAS:
            dia += timedelta(days=1)
            vueltas += 1
            if dia.weekday() in laborables and dia not in feriados:
                puestos += 1
        return dia

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
        "guvens_remito_requiere_hes",
        "guvens_motivo_no_facturado",
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
                if hay_posteadas:
                    picking.guvens_plazo_estado = "indeterminado"
                elif picking.guvens_motivo_no_facturado == "sin_factura":
                    # No está esperando: nadie va a facturarlo. Si quedara «pendiente»
                    # envejecería para siempre y treparía en el ranking de demoras.
                    picking.guvens_plazo_estado = "no_factura"
                else:
                    picking.guvens_plazo_estado = "pendiente"
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

            if picking.guvens_remito_requiere_hes:
                # Se le miden los días igual —Franco quiere comparar los dos grupos—
                # pero no se le reclama el plazo: facturar no depende de nosotros.
                # Se mira el tilde DEL REMITO y no la lista del cliente: el mismo
                # cliente puede exigir la HES en una entrega y no en la siguiente.
                picking.guvens_plazo_estado = "hes"
                continue

            plazo = picking.company_id.guvens_plazo_facturacion_dias
            if not plazo:
                picking.guvens_plazo_estado = "facturado"
            else:
                picking.guvens_plazo_estado = "en_plazo" if dias <= plazo else "excedido"

    @api.depends("guvens_remito_requiere_hes")
    def _compute_guvens_motivo_no_facturado(self):
        """Propone «espera HES» desde el tilde; lo demás lo marca quien factura.

        Es un compute EDITABLE, igual que el tilde: el sistema sabe cuándo se está
        esperando una HES —lo dice el tilde—, pero no puede saber si el cliente no
        pasó a retirar o si esa entrega no lleva comprobante. Eso lo sabe la persona.

        Depende sólo del tilde: al marcarlo o destildarlo el motivo se vuelve a
        proponer, porque cambió el hecho del que salía. Un motivo cargado a mano
        sobre un remito cuyo tilde nadie toca se queda como está.
        """
        for picking in self:
            if picking.guvens_remito_requiere_hes:
                picking.guvens_motivo_no_facturado = "espera_hes"
            elif picking.guvens_motivo_no_facturado == "espera_hes":
                # Se destildó: el motivo que había salido del tilde ya no vale.
                picking.guvens_motivo_no_facturado = False
            else:
                # Se reasigna su propio valor a propósito: un compute almacenado tiene
                # que dejar todos los registros asignados, y acá la rama que no hace
                # nada es justamente la del motivo que cargó una persona.
                picking.guvens_motivo_no_facturado = picking.guvens_motivo_no_facturado

    @api.depends("guvens_remito_fecha", "guvens_plazo_estado")
    def _compute_guvens_dias_sin_facturar(self):
        """Lo que lleva esperando un remito sin factura, hasta hoy.

        Depende del estado y no de la factura directamente: así se apaga solo en
        cuanto el remito pasa a cualquier estado que ya tenga factura.

        «Hoy» no es un campo, así que este cálculo envejece sin que nada lo marque
        como sucio. Lo refresca el cron `cron_dias_sin_facturar`, una vez por día.
        """
        for picking in self:
            if picking.guvens_plazo_estado != "pendiente" or not picking.guvens_remito_fecha:
                picking.guvens_dias_sin_facturar = 0
                continue
            desde = picking._guvens_fecha_local(picking.guvens_remito_fecha)
            picking.guvens_dias_sin_facturar = picking._guvens_dias_habiles(
                desde, fields.Date.context_today(picking))

    @api.model
    def _guvens_cron_dias_sin_facturar(self):
        """Refresca la espera en curso de los remitos pendientes.

        Acotado a los que están esperando —unas decenas—, no a todos los albaranes.
        Los que ya se facturaron tienen el campo en cero y no cambian más.
        """
        pendientes = self.search([
            ("guvens_remito_fecha", "!=", False),
            ("guvens_plazo_estado", "=", "pendiente"),
        ])
        if pendientes:
            pendientes.modified(["guvens_plazo_estado"])
        return len(pendientes)

    # ------------------------------------------------------------------
    #  Aviso para facturar
    # ------------------------------------------------------------------
    def _guvens_tipo_actividad_aviso(self):
        return self.env.ref("surtecnica_remito.activity_facturar_remito",
                            raise_if_not_found=False)

    def _guvens_actividades_de_aviso(self):
        """Los avisos abiertos de este remito, para no duplicarlos ni dejarlos colgados."""
        tipo = self._guvens_tipo_actividad_aviso()
        if not tipo:
            return self.env["mail.activity"]
        return self.env["mail.activity"].search([
            ("res_model", "=", "stock.picking"),
            ("res_id", "in", self.ids),
            ("activity_type_id", "=", tipo.id),
        ])

    def _guvens_crear_aviso_facturar(self):
        """Avisa a quien factura que hay un remito confeccionado.

        El aviso es GENÉRICO: se crea para todos los clientes, también para los que
        exigen HES. Franco lo pidió así —«lo podemos configurar como genérico esa
        alerta y le quedarán como pendiente a aquellos clientes que todavía no
        tengan la HES»—: en esos casos el aviso queda abierto hasta que llegue el
        código, en vez de no existir. Si no se creara, cuando el cliente manda la
        HES no habría nada que le recuerde a nadie emitir la factura.

        Lo que NO corresponde a los clientes con HES es reclamarles el plazo, y eso
        se resuelve del otro lado: el indicador los marca «Cliente con HES» y nunca
        «Excedido».

        No se avisa si: no hay destinatario cargado en la compañía, el remito ya
        tiene factura, o ya hay un aviso abierto.
        """
        tipo = self._guvens_tipo_actividad_aviso()
        if not tipo:
            return
        for picking in self:
            destinatario = picking.company_id.guvens_aviso_facturacion_user_id
            if not destinatario or not picking.guvens_remito_fecha:
                continue
            if picking.guvens_factura_id:
                continue
            if picking._guvens_actividades_de_aviso():
                continue

            dia = picking._guvens_fecha_local(picking.guvens_remito_fecha)
            plazo = picking.company_id.guvens_plazo_facturacion_dias
            vence = picking._guvens_sumar_habiles(dia, plazo) if plazo else dia
            picking.activity_schedule(
                "surtecnica_remito.activity_facturar_remito",
                date_deadline=vence,
                user_id=destinatario.id,
                note=_("Remito %(numero)s de %(cliente)s — confeccionado el %(fecha)s%(espera)s",
                       numero=picking.guvens_remito_number or picking.name,
                       # sin punto final: muchas razones sociales ya terminan en
                       # uno («4 L S.A.») y quedaba «S.A..»
                       cliente=(picking.partner_id.display_name or "-").rstrip("."),
                       fecha=dia.strftime("%d/%m/%Y"),
                       espera=_(". Este cliente factura contra HES: queda pendiente "
                                "hasta que mande el código.")
                       if picking.guvens_remito_requiere_hes else ""),
            )

    def action_guvens_generar_avisos_pendientes(self, dias_max=7):
        """Genera el aviso de los remitos pendientes CONFECCIONADOS HACE POCO.

        El aviso se crea al cargar el número del talonario, así que al activar la
        función los remitos anteriores quedan sin él. Pero no se avisan todos: uno
        de hace cincuenta días ya tiene el plazo vencido hace rato y avisarlo no
        cambia nada operativo, sólo llena la bandeja. Y una bandeja llena de cosas
        viejas es una bandeja que se deja de mirar, que es la forma más segura de
        que el aviso no sirva para nada.

        `dias_max` son días corridos hacia atrás desde hoy.

        Es una acción explícita y no algo automático: crear avisos de golpe en la
        bandeja de alguien es una decisión, no un efecto secundario del despliegue.
        Se puede correr las veces que haga falta, porque no duplica.
        """
        corte = fields.Datetime.now() - timedelta(days=dias_max)
        pendientes = self.search([
            ("guvens_plazo_estado", "=", "pendiente"),
            ("guvens_remito_fecha", ">=", fields.Datetime.to_string(corte)),
            ("company_id", "in", self.env.companies.ids),
        ])
        antes = len(pendientes._guvens_actividades_de_aviso())
        pendientes._guvens_crear_aviso_facturar()
        creados = len(pendientes._guvens_actividades_de_aviso()) - antes
        return creados

    def _guvens_cerrar_aviso_facturar(self):
        """Cierra el aviso cuando el remito ya tiene factura.

        Sin esto quedan actividades vencidas de remitos ya facturados, que es ruido
        en la bandeja de quien factura y hace que deje de mirarlas.
        """
        actividades = self._guvens_actividades_de_aviso()
        if actividades:
            actividades.action_feedback(feedback=_("Facturado."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("guvens_remito_number"):
                vals["guvens_remito_number"] = vals["guvens_remito_number"].strip()
                vals.setdefault("guvens_remito_fecha", fields.Datetime.now())
        pickings = super().create(vals_list)
        pickings.filtered("guvens_remito_fecha")._guvens_crear_aviso_facturar()
        return pickings

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
                sin_sello._guvens_crear_aviso_facturar()
        elif "guvens_remito_number" in vals:
            # Le borraron el número: el remito dejó de estar confeccionado y el aviso
            # ya no corresponde.
            self._guvens_actividades_de_aviso().unlink()
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
