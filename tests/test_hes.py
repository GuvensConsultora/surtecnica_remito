from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install")
class TestRequiereHes(TransactionCase):
    """El campo de HES es un dato puro, sin lógica: lo que hay que proteger no es un
    cálculo sino la decisión de que nace vacío y lo carga administración.

    Quién exige HES no se puede deducir del sistema, así que cualquier valor que el
    módulo trajera puesto sería una suposición nuestra sobre el circuito del cliente.
    Y el costo de equivocarse no es simétrico: marcar de más silencia el plazo de un
    cliente al que sí había que reclamarle, y eso no se nota —el indicador simplemente
    deja de contarlo—.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente de prueba HES"})

    def test_nace_desmarcado(self):
        """Un cliente nuevo no requiere HES hasta que alguien lo diga."""
        self.assertFalse(self.cliente.guvens_requiere_hes)

    def test_instalar_no_marca_a_nadie(self):
        """Instalar el módulo no debe dejar ningún cliente marcado.

        Es el control de que no entró una lista precargada por código ni por datos
        semilla: la carga es cliente por cliente y la hace administración.
        """
        marcados = self.env["res.partner"].search_count([
            ("guvens_requiere_hes", "=", True),
        ])
        self.assertEqual(
            marcados, 0,
            "Hay clientes marcados como 'requiere HES' sin que nadie los haya cargado.",
        )

    def test_se_puede_marcar_y_filtrar(self):
        """El campo tiene que estar almacenado: el indicador agrupa por él."""
        self.cliente.guvens_requiere_hes = True
        encontrados = self.env["res.partner"].search([
            ("guvens_requiere_hes", "=", True),
            ("id", "=", self.cliente.id),
        ])
        self.assertEqual(encontrados, self.cliente)

    def test_vale_igual_en_las_dos_companias(self):
        """El requisito lo impone el cliente, no nuestra razón social.

        Por eso el campo no es company_dependent: si lo fuera, marcarlo en una
        compañía dejaría al mismo cliente sin marcar en la otra y el indicador le
        reclamaría un plazo que no corresponde.
        """
        companias = self.env["res.company"].search([], limit=2)
        if len(companias) < 2:
            self.skipTest("La base tiene una sola compañía")
        self.cliente.guvens_requiere_hes = True
        otra = self.cliente.with_company(companias[1])
        self.assertTrue(otra.guvens_requiere_hes)


@tagged("post_install", "-at_install")
class TestTildeHesDelRemito(TransactionCase):
    """El tilde del remito: nace del cliente y después manda el remito.

    Lo que protege este bloque es la asimetría que pidió Franco: la lista del cliente
    es un valor inicial, no una regla. «Cada cliente es distinto. Entonces no sé de
    ante mano todas las excepciones» — el mismo cliente exige la HES por un servicio
    y no por una entrega de rodillos. Si la lista decidiera, esa excepción no se
    podría registrar y el indicador silenciaría un plazo que sí había que reclamar.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.con_hes = cls.env["res.partner"].create({
            "name": "Cliente que exige HES",
            "guvens_requiere_hes": True,
        })
        cls.sin_hes = cls.env["res.partner"].create({"name": "Cliente sin HES"})
        cls.tipo = cls.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def _remito(self, cliente, numero=False):
        vals = {
            "partner_id": cliente.id,
            "picking_type_id": self.tipo.id,
            "location_id": self.tipo.default_location_src_id.id,
            "location_dest_id": self.tipo.default_location_dest_id.id,
        }
        if numero:
            vals["guvens_remito_number"] = numero
        return self.env["stock.picking"].create(vals)

    def test_nace_marcado_si_el_cliente_esta_en_la_lista(self):
        self.assertTrue(self._remito(self.con_hes).guvens_remito_requiere_hes)

    def test_nace_desmarcado_si_el_cliente_no_esta(self):
        self.assertFalse(self._remito(self.sin_hes).guvens_remito_requiere_hes)

    def test_se_puede_destildar_y_queda_destildado(self):
        """La excepción del caso Mansfield: cliente con HES, entrega que no la lleva."""
        remito = self._remito(self.con_hes)
        remito.guvens_remito_requiere_hes = False
        remito.invalidate_recordset()
        self.assertFalse(remito.guvens_remito_requiere_hes)

    def test_se_puede_marcar_a_mano_en_un_cliente_que_no_esta_en_la_lista(self):
        """Al revés también: una entrega puntual que sí necesita autorización."""
        remito = self._remito(self.sin_hes)
        remito.guvens_remito_requiere_hes = True
        remito.invalidate_recordset()
        self.assertTrue(remito.guvens_remito_requiere_hes)

    def test_marcar_al_cliente_despues_no_pisa_el_remito(self):
        """Cargar la lista no debe mover remitos ya confeccionados.

        Es la razón por la que el compute depende de `partner_id` y no del campo del
        cliente: administración va a ir cargando la lista con remitos ya hechos, y un
        recálculo ahí borraría los destildes que alguien puso a mano.
        """
        remito = self._remito(self.sin_hes, numero="0002-00099001")
        self.sin_hes.guvens_requiere_hes = True
        remito.invalidate_recordset()
        self.assertFalse(remito.guvens_remito_requiere_hes)

    def test_cambiar_el_cliente_recalcula(self):
        """Si cambia el cliente del albarán, cambió el hecho del que salía el tilde."""
        remito = self._remito(self.sin_hes)
        remito.partner_id = self.con_hes
        self.assertTrue(remito.guvens_remito_requiere_hes)

    # ---------------- efecto sobre el indicador ----------------
    def test_sin_factura_el_tilde_no_cambia_el_estado(self):
        """El estado «Espera HES» recién aparece cuando hay factura para medir.

        Hasta entonces el remito está «Pendiente de facturar», tilde o no: lo que
        el tilde define es si, una vez facturado, se le reclama el plazo. Ese tramo
        del cálculo necesita una factura posteada —que en una base argentina exige
        punto de venta y tipo de documento— y se verifica contra los remitos reales
        de testing, igual que los demás estados con factura (ver `test_plazo`).
        """
        remito = self._remito(self.con_hes, numero="0002-00099002")
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")
        remito.guvens_remito_requiere_hes = False
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")

    def test_el_estado_depende_del_tilde_y_no_del_cliente(self):
        """El `@api.depends` del plazo tiene que escuchar al tilde del remito.

        No se mide el estado final —para eso hace falta la factura— sino que el
        cálculo se vuelva a disparar al tocar el tilde. Si quedara escuchando a
        `partner_id.guvens_requiere_hes`, destildar no recalcularía nada y el remito
        seguiría silenciado con el estado viejo.
        """
        campos = self.env["stock.picking"]._fields["guvens_plazo_estado"].depends
        self.assertIn("guvens_remito_requiere_hes", campos)
        self.assertNotIn("partner_id.guvens_requiere_hes", campos)

    def test_la_nota_del_aviso_sigue_al_tilde(self):
        """Destildado, el aviso no debe decirle a nadie que espere una HES."""
        self.env.company.guvens_aviso_facturacion_user_id = self.env.ref("base.user_admin")
        remito = self._remito(self.con_hes)
        remito.guvens_remito_requiere_hes = False
        remito.guvens_remito_number = "0002-00099004"
        aviso = self.env["mail.activity"].search([
            ("res_model", "=", "stock.picking"), ("res_id", "=", remito.id)])
        self.assertEqual(len(aviso), 1)
        self.assertNotIn("HES", aviso.note or "")


@tagged("post_install", "-at_install")
class TestPantallaClientesHes(TransactionCase):
    """La pantalla para cargar la lista: lo que se protege es su dominio.

    Si filtrara sólo por `customer_rank > 0`, un cliente marcado que todavía no
    registra ventas quedaría marcado y fuera de la pantalla: nadie podría volver a
    encontrarlo para desmarcarlo, y sus remitos seguirían naciendo con el tilde sin
    que se vea por qué.
    """

    def test_el_dominio_alcanza_a_un_marcado_sin_ventas(self):
        accion = self.env.ref("surtecnica_remito.action_clientes_hes")
        marcado = self.env["res.partner"].create({
            "name": "Cliente marcado sin ventas",
            "guvens_requiere_hes": True,
        })
        self.assertEqual(marcado.customer_rank, 0)
        encontrados = self.env["res.partner"].search(
            safe_eval(accion.domain) + [("id", "=", marcado.id)])
        self.assertEqual(encontrados, marcado)

    def test_la_lista_no_deja_crear_ni_borrar_contactos(self):
        """Un alta de contacto hecha de paso acá sería un duplicado."""
        vista = self.env.ref("surtecnica_remito.view_partner_tree_hes")
        self.assertIn('create="0"', vista.arch)
        self.assertIn('delete="0"', vista.arch)

    def test_el_menu_no_lo_ve_quien_solo_arma_remitos(self):
        """La lista la maneja quien factura; en el remito se destilda y nada más.

        El corte no puede ser por grupo de inventario: en esta instancia quien arma
        los remitos es Administrador de Inventario y quien factura es sólo Usuario.
        """
        menu = self.env.ref("surtecnica_remito.menu_clientes_hes")
        self.assertEqual(
            menu.groups_id,
            self.env.ref("account.group_account_invoice"),
        )
