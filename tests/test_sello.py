from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSelloRemito(TransactionCase):
    """El sello de confección es el que arranca el reloj del plazo de facturación.

    Es el dato más frágil del indicador: el número del talonario se puede volver a
    cargar, pero el momento en que se cargó, una vez pisado, no se recupera de
    ningún lado.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente de prueba sello"})
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

    def test_crear_con_numero_estampa_el_sello(self):
        remito = self._remito("9001-00000001")
        self.assertTrue(remito.guvens_remito_fecha)

    def test_crear_sin_numero_no_estampa(self):
        """Sin número no hay remito confeccionado, así que no hay reloj."""
        remito = self._remito()
        self.assertFalse(remito.guvens_remito_fecha)

    def test_cargar_el_numero_estampa_el_sello(self):
        remito = self._remito()
        remito.guvens_remito_number = "9001-00000002"
        self.assertTrue(remito.guvens_remito_fecha)

    def test_corregir_el_numero_no_mueve_el_sello(self):
        """Un dígito mal tipeado no es volver a confeccionar el remito."""
        remito = self._remito("9001-00000003")
        sello = remito.guvens_remito_fecha
        remito.guvens_remito_number = "9001-00000004"
        self.assertEqual(remito.guvens_remito_fecha, sello)

    def test_borrar_el_numero_limpia_el_sello(self):
        """Sin número vuelve a no estar confeccionado: el reloj no puede seguir corriendo."""
        remito = self._remito("9001-00000005")
        self.assertTrue(remito.guvens_remito_fecha)
        remito.guvens_remito_number = False
        self.assertFalse(remito.guvens_remito_fecha)

    def test_write_masivo_no_pisa_un_sello_existente(self):
        """El caso que el `write` evita poniendo el sello fuera de `vals`.

        Un mismo write puede alcanzar varios albaranes, unos con sello y otros sin
        él; si la fecha viajara dentro de `vals`, se la pisaría a los que ya la
        tenían. El constraint de unicidad es por compañía, así que el único
        escenario real donde dos albaranes reciben el mismo número en un solo write
        es entre compañías distintas.
        """
        otra = self.env["res.company"].search([("id", "!=", self.env.company.id)], limit=1)
        tipo_otra = self.env["stock.picking.type"].search([
            ("code", "=", "outgoing"), ("company_id", "=", otra.id),
        ], limit=1) if otra else False
        if not tipo_otra:
            self.skipTest("No hay una segunda compañía con operaciones de salida")

        viejo = self._remito("9001-00000006")
        sello_previo = viejo.guvens_remito_fecha
        nuevo = self.env["stock.picking"].create({
            "partner_id": self.cliente.id,
            "picking_type_id": tipo_otra.id,
            "location_id": tipo_otra.default_location_src_id.id,
            "location_dest_id": tipo_otra.default_location_dest_id.id,
            "company_id": otra.id,
        })
        self.assertFalse(nuevo.guvens_remito_fecha)

        (viejo | nuevo).write({"guvens_remito_number": "9001-00000006"})

        self.assertEqual(viejo.guvens_remito_fecha, sello_previo,
                         "Se pisó el sello de un remito que ya estaba confeccionado.")
        self.assertTrue(nuevo.guvens_remito_fecha,
                        "El remito nuevo quedó sin sello.")
