from datetime import date, datetime, time, timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged

# Semana de referencia: el 16/10/2026 es viernes, el 19 lunes, el 20 martes y el
# 23 viernes. Elegida a propósito para que los fines de semana queden en el medio.
VIERNES = date(2026, 10, 16)
LUNES = date(2026, 10, 19)
MARTES = date(2026, 10, 20)
VIERNES_SIGUIENTE = date(2026, 10, 23)


@tagged("post_install", "-at_install")
class TestPlazoFacturacion(TransactionCase):
    """Cubre el cálculo, que es donde está la lógica delicada.

    Los estados que necesitan una factura posteada (en plazo, excedido, previo,
    indeterminado) no se arman acá con una factura sintética: postear en una base
    argentina exige punto de venta y tipo de documento, y un test que falla por eso
    no dice nada del plazo. Esos se verifican contra los remitos reales de testing,
    que además son el caso de verdad.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente de prueba plazo"})
        cls.tipo = cls.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def _remito(self, numero=False):
        vals = {
            "partner_id": self.cliente.id,
            "picking_type_id": self.tipo.id,
            "location_id": self.tipo.default_location_src_id.id,
            "location_dest_id": self.tipo.default_location_dest_id.id,
        }
        if numero:
            vals["guvens_remito_number"] = numero
        return self.env["stock.picking"].create(vals)

    # ---------------- días hábiles ----------------
    def test_mismo_dia_no_suma(self):
        self.assertEqual(self._remito()._guvens_dias_habiles(VIERNES, VIERNES), 0)

    def test_el_fin_de_semana_no_cuenta(self):
        """Viernes a lunes es UN día hábil, no tres."""
        self.assertEqual(self._remito()._guvens_dias_habiles(VIERNES, LUNES), 1)

    def test_viernes_a_martes_son_dos(self):
        """El ejemplo que le dimos a Franco: remito el viernes, vence el martes."""
        self.assertEqual(self._remito()._guvens_dias_habiles(VIERNES, MARTES), 2)

    def test_una_semana_son_cinco(self):
        self.assertEqual(
            self._remito()._guvens_dias_habiles(VIERNES, VIERNES_SIGUIENTE), 5)

    def test_una_factura_anterior_no_da_negativo(self):
        self.assertEqual(self._remito()._guvens_dias_habiles(MARTES, VIERNES), 0)

    def test_un_feriado_cargado_deja_de_contar(self):
        """Hoy el calendario no tiene feriados, así que cuentan como hábiles.

        El cálculo no los trae de ningún lado: los toma del calendario laboral. Este
        test carga uno y comprueba que efectivamente deja de sumar, que es lo que va
        a pasar en cuanto alguien los cargue.
        """
        remito = self._remito()
        calendario = remito.company_id.resource_calendar_id
        if not calendario:
            self.skipTest("La compañía no tiene calendario laboral")
        sin_feriado = remito._guvens_dias_habiles(VIERNES, MARTES)
        self.env["resource.calendar.leaves"].create({
            "name": "Feriado de prueba",
            "calendar_id": calendario.id,
            "date_from": datetime(2026, 10, 19, 3, 0, 0),
            "date_to": datetime(2026, 10, 20, 2, 59, 0),
        })
        remito.invalidate_recordset()
        con_feriado = remito._guvens_dias_habiles(VIERNES, MARTES)
        self.assertEqual(sin_feriado, 2)
        self.assertEqual(con_feriado, 1, "El feriado del lunes siguió contando")

    # ---------------- zona horaria ----------------
    def test_un_remito_del_viernes_a_la_noche_es_del_viernes(self):
        """El bug que este helper evita.

        Los Datetime de Odoo son UTC. Un remito cargado el viernes 22:30 de acá
        figura como sábado 01:30 en la base. Sin convertir, el reloj arrancaría el
        fin de semana y el remito perdería un día entero de plazo.
        """
        remito = self._remito()
        guardado_en_la_base = datetime(2026, 10, 17, 1, 30, 0)  # sábado en UTC
        self.assertEqual(remito._guvens_fecha_local(guardado_en_la_base), VIERNES)

    # ---------------- estados ----------------
    def test_sin_numero_no_hay_estado(self):
        """Sin remito confeccionado no hay reloj que mirar."""
        self.assertFalse(self._remito().guvens_plazo_estado)

    def test_con_numero_y_sin_factura_queda_pendiente(self):
        remito = self._remito("9002-00000001")
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")
        self.assertEqual(remito.guvens_dias_a_factura, 0)


@tagged("post_install", "-at_install")
class TestFeriados(TransactionCase):
    """Los feriados: qué día es feriado, y que el indicador se entere.

    Los dos defectos que cubre este bloque se midieron en vivo en testing el
    21/10/2026, antes de cargarle los feriados reales al calendario: un feriado
    cargado como día local completo bajaba un remito de 4 días hábiles a 2, y al
    borrarlo el remito se quedaba con los días que había calculado con él.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente de feriados"})
        cls.tipo = cls.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def _remito(self, numero=False):
        vals = {
            "partner_id": self.cliente.id,
            "picking_type_id": self.tipo.id,
            "location_id": self.tipo.default_location_src_id.id,
            "location_dest_id": self.tipo.default_location_dest_id.id,
        }
        if numero:
            vals["guvens_remito_number"] = numero
        return self.env["stock.picking"].create(vals)

    def _feriado(self, calendario, dia):
        """Un feriado como lo carga la pantalla de Odoo: el día local completo.

        En hora de acá son las 00:00 y las 23:59 del mismo día; guardado en UTC, el
        extremo de arriba cae en el día siguiente.
        """
        return self.env["resource.calendar.leaves"].create({
            "name": f"Feriado de prueba {dia}",
            "calendar_id": calendario.id,
            "date_from": datetime.combine(dia, time(3, 0)),
            "date_to": datetime.combine(dia + timedelta(days=1), time(2, 59)),
        })

    def test_el_feriado_resta_un_solo_dia(self):
        """Lo que fallaba: el día siguiente dejaba de contar sin estar marcado."""
        remito = self._remito()
        calendario = remito.company_id.resource_calendar_id
        if not calendario:
            self.skipTest("La compañía no tiene calendario laboral")
        self.assertEqual(remito._guvens_dias_habiles(VIERNES, VIERNES_SIGUIENTE), 5)
        self._feriado(calendario, LUNES)
        remito.invalidate_recordset()
        self.assertEqual(
            remito._guvens_dias_habiles(VIERNES, VIERNES_SIGUIENTE), 4,
            "El feriado del lunes tiene que restar un día, no dos",
        )
        self.assertEqual(
            remito._guvens_dias_habiles(MARTES, VIERNES_SIGUIENTE), 3,
            "El martes siguiente al feriado siguió siendo hábil",
        )

    def test_un_feriado_cargado_en_utc_tambien_resta_uno(self):
        """Al revés: cargado de 00:00 a 23:59 UTC, el día local anterior no se toca."""
        remito = self._remito()
        calendario = remito.company_id.resource_calendar_id
        if not calendario:
            self.skipTest("La compañía no tiene calendario laboral")
        self.env["resource.calendar.leaves"].create({
            "name": "Feriado cargado por script",
            "calendar_id": calendario.id,
            "date_from": datetime.combine(LUNES, time(0, 0)),
            "date_to": datetime.combine(LUNES, time(23, 59)),
        })
        remito.invalidate_recordset()
        self.assertEqual(remito._guvens_dias_habiles(VIERNES, VIERNES_SIGUIENTE), 4)

    def test_cargar_un_feriado_recalcula_los_remitos(self):
        """El indicador tiene que enterarse: los feriados no están en el depends."""
        remito = self._remito(numero="0002-00088001")
        calendario = remito.company_id.resource_calendar_id
        if not calendario:
            self.skipTest("La compañía no tiene calendario laboral")
        self.assertTrue(remito.guvens_remito_fecha)
        ausencia = self._feriado(calendario, LUNES)
        # El recálculo se dispara desde el create de la ausencia: lo que se comprueba
        # es que los remitos con sello quedaron marcados para recomputar.
        self.assertIn(remito, ausencia._guvens_remitos_a_recalcular())

    def test_borrar_un_feriado_tambien_recalcula(self):
        remito = self._remito(numero="0002-00088002")
        calendario = remito.company_id.resource_calendar_id
        if not calendario:
            self.skipTest("La compañía no tiene calendario laboral")
        ausencia = self._feriado(calendario, LUNES)
        self.assertIn(remito, ausencia._guvens_remitos_a_recalcular())
        ausencia.unlink()
        remito.invalidate_recordset()
        self.assertEqual(remito._guvens_dias_habiles(VIERNES, VIERNES_SIGUIENTE), 5)


@tagged("post_install", "-at_install")
class TestDiasSinFacturar(TransactionCase):
    """La espera en curso: lo que el promedio de los facturados no muestra.

    Medido en testing el 21/10/2026: el cliente que la empresa considera el más
    lento tenía 7 remitos y los 7 sin facturar, así que no aparecía en ningún
    promedio. Medir sólo lo facturado premia al que más se cuelga.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente que no factura"})
        cls.tipo = cls.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def _remito(self, numero=False):
        vals = {
            "partner_id": self.cliente.id,
            "picking_type_id": self.tipo.id,
            "location_id": self.tipo.default_location_src_id.id,
            "location_dest_id": self.tipo.default_location_dest_id.id,
        }
        if numero:
            vals["guvens_remito_number"] = numero
        return self.env["stock.picking"].create(vals)

    def test_un_remito_sin_sello_no_espera_nada(self):
        self.assertEqual(self._remito().guvens_dias_sin_facturar, 0)

    def test_cuenta_los_dias_habiles_hasta_hoy(self):
        """El sello se fuerza hacia atrás para no depender de la fecha del test."""
        remito = self._remito(numero="0002-00077001")
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")
        hoy = fields.Date.context_today(remito)
        remito.guvens_remito_fecha = datetime.combine(hoy, time(12, 0)) - timedelta(days=14)
        remito.invalidate_recordset()
        esperado = remito._guvens_dias_habiles(
            remito._guvens_fecha_local(remito.guvens_remito_fecha), hoy)
        self.assertEqual(remito.guvens_dias_sin_facturar, esperado)
        self.assertGreater(remito.guvens_dias_sin_facturar, 0,
                           "Catorce días corridos tienen que dejar días hábiles")

    def test_el_cron_alcanza_a_los_pendientes(self):
        remito = self._remito(numero="0002-00077002")
        tocados = self.env["stock.picking"]._guvens_cron_dias_sin_facturar()
        self.assertGreaterEqual(tocados, 1)
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")

    def test_el_cron_existe_y_esta_activo(self):
        """Sin el cron el número se congela el día que se calculó, sin avisar."""
        cron = self.env.ref("surtecnica_remito.cron_dias_sin_facturar")
        self.assertTrue(cron.active)
        self.assertEqual(cron.interval_type, "days")
        self.assertEqual(cron.interval_number, 1)


@tagged("post_install", "-at_install")
class TestMotivoNoFacturado(TransactionCase):
    """El motivo: sin él, el ranking de demoras mezcla atrasos con lo que no lo es.

    Medido el 21/10/2026 sobre los remitos reales de testing: los dos primeros
    puestos del ranking de espera eran un remito que el cliente nunca pasó a retirar
    y uno que directamente no se factura. Ninguno de los dos es un atraso nuestro ni
    del cliente en autorizar.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente motivos"})
        cls.con_hes = cls.env["res.partner"].create({
            "name": "Cliente motivos con HES", "guvens_requiere_hes": True})
        cls.tipo = cls.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def _remito(self, numero=False, cliente=None):
        vals = {
            "partner_id": (cliente or self.cliente).id,
            "picking_type_id": self.tipo.id,
            "location_id": self.tipo.default_location_src_id.id,
            "location_dest_id": self.tipo.default_location_dest_id.id,
        }
        if numero:
            vals["guvens_remito_number"] = numero
        return self.env["stock.picking"].create(vals)

    def test_el_tilde_propone_el_motivo(self):
        self.assertEqual(
            self._remito(cliente=self.con_hes).guvens_motivo_no_facturado, "espera_hes")

    def test_destildar_saca_el_motivo_propuesto(self):
        remito = self._remito(cliente=self.con_hes)
        remito.guvens_remito_requiere_hes = False
        self.assertFalse(remito.guvens_motivo_no_facturado)

    def test_un_motivo_cargado_a_mano_no_se_pisa(self):
        """Lo que carga una persona manda sobre lo que propone el sistema."""
        remito = self._remito(numero="0002-00066001")
        remito.guvens_motivo_no_facturado = "no_retiro"
        remito.guvens_remito_requiere_hes = False   # vuelve a disparar el compute
        self.assertEqual(remito.guvens_motivo_no_facturado, "no_retiro")

    def test_sin_factura_sale_de_pendiente_y_deja_de_esperar(self):
        """Si nadie va a facturarlo, no está esperando: no puede seguir envejeciendo."""
        remito = self._remito(numero="0002-00066002")
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")
        remito.guvens_remito_fecha = datetime.now() - timedelta(days=30)
        remito.invalidate_recordset()
        self.assertGreater(remito.guvens_dias_sin_facturar, 0)
        remito.guvens_motivo_no_facturado = "sin_factura"
        self.assertEqual(remito.guvens_plazo_estado, "no_factura")
        self.assertEqual(remito.guvens_dias_sin_facturar, 0)

    def test_no_retiro_sigue_contando_la_espera(self):
        """No es lo mismo que «no se factura»: acá la factura todavía va a existir."""
        remito = self._remito(numero="0002-00066003")
        remito.guvens_remito_fecha = datetime.now() - timedelta(days=30)
        remito.guvens_motivo_no_facturado = "no_retiro"
        remito.invalidate_recordset()
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")
        self.assertGreater(remito.guvens_dias_sin_facturar, 0)
