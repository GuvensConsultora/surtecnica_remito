from datetime import date

from odoo.tests import TransactionCase, tagged

VIERNES = date(2026, 10, 16)


@tagged("post_install", "-at_install")
class TestAvisoFacturar(TransactionCase):
    """El aviso tiene dos riesgos opuestos y los dos son caros.

    Si no llega, el plazo no se cumple y el indicador sólo sirve para mirar el
    desastre después. Si llega de más —a clientes con HES, repetido, o sobre
    remitos ya facturados— la bandeja se llena de ruido, la persona deja de
    mirarla, y el aviso pasa a no existir aunque técnicamente funcione.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente aviso"})
        cls.tipo = cls.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        cls.destinatario = cls.env["res.users"].search([("share", "=", False)], limit=1)

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

    def _avisos(self, remito):
        return remito._guvens_actividades_de_aviso()

    def test_sin_destinatario_no_avisa_a_nadie(self):
        """El campo nace vacío: mientras lo esté, el módulo no genera actividades."""
        self.env.company.guvens_aviso_facturacion_user_id = False
        remito = self._remito("9003-00000001")
        self.assertFalse(self._avisos(remito))

    def test_con_destinatario_avisa_al_confeccionar(self):
        self.env.company.guvens_aviso_facturacion_user_id = self.destinatario
        remito = self._remito("9003-00000002")
        avisos = self._avisos(remito)
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos.user_id, self.destinatario)

    def test_no_avisa_dos_veces_por_el_mismo_remito(self):
        """Corregir el número no es confeccionar otro remito."""
        self.env.company.guvens_aviso_facturacion_user_id = self.destinatario
        remito = self._remito("9003-00000003")
        remito.guvens_remito_number = "9003-00000004"
        self.assertEqual(len(self._avisos(remito)), 1)

    def test_tambien_avisa_si_el_cliente_exige_hes(self):
        """El aviso es genérico, como lo pidió Franco.

        A esos clientes el aviso les queda pendiente hasta que mande el código, en
        vez de no existir: si no se creara, cuando llega la HES no habría nada que
        le recuerde a nadie emitir la factura. Lo que no corresponde es reclamarles
        el plazo, y de eso se ocupa el indicador, que los marca «Cliente con HES».
        """
        self.env.company.guvens_aviso_facturacion_user_id = self.destinatario
        conhes = self.env["res.partner"].create({
            "name": "Cliente con HES", "guvens_requiere_hes": True})
        remito = self._remito("9003-00000005", cliente=conhes)
        avisos = self._avisos(remito)
        self.assertEqual(len(avisos), 1)
        self.assertIn("HES", avisos.note or "")

    def test_borrar_el_numero_saca_el_aviso(self):
        self.env.company.guvens_aviso_facturacion_user_id = self.destinatario
        remito = self._remito("9003-00000006")
        self.assertTrue(self._avisos(remito))
        remito.guvens_remito_number = False
        self.assertFalse(self._avisos(remito))

    def test_el_vencimiento_salta_el_fin_de_semana(self):
        """Dos días hábiles desde un viernes vencen el martes, no el domingo."""
        self.env.company.guvens_plazo_facturacion_dias = 2
        remito = self._remito()
        self.assertEqual(remito._guvens_sumar_habiles(VIERNES, 2), date(2026, 10, 20))

    def test_sumar_cero_dias_no_mueve_la_fecha(self):
        self.assertEqual(self._remito()._guvens_sumar_habiles(VIERNES, 0), VIERNES)
