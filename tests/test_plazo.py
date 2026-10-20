from datetime import date, datetime

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
