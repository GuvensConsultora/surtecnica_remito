from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestValorSinFacturar(TransactionCase):
    """Cubre la valorización del remito sin factura.

    Los tests arman un pedido de verdad y lo confirman, porque lo que se está
    probando es justamente la cadena pedido → línea → movimiento: el precio vive en
    la línea, la cantidad en el movimiento, y cada uno en su unidad de medida.

    La cantidad del movimiento se escribe a mano en vez de dejarla salir de la
    reserva: sin stock cargado la reserva da cero y el test fallaría por el
    inventario, no por el cálculo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente valor sin facturar"})
        cls.unidad = cls.env.ref("uom.product_uom_unit")
        cls.docena = cls.env.ref("uom.product_uom_dozen")
        cls.producto = cls.env["product.product"].create({
            "name": "Producto valor sin facturar",
            # Consumible a propósito: no se reserva ni exige existencias.
            "type": "consu",
            "uom_id": cls.unidad.id,
            "uom_po_id": cls.unidad.id,
            "list_price": 100.0,
        })
        # Moneda propia, con tipo de cambio propio: así el valor en pesos es un
        # número exacto y no depende de las cotizaciones que ya tenga la base.
        cls.moneda = cls.env["res.currency"].create({
            "name": "VSF",
            "symbol": "V",
            "rounding": 0.01,
        })
        cls.env["res.currency.rate"].create({
            "currency_id": cls.moneda.id,
            "company_id": cls.env.company.id,
            "rate": 0.5,  # 1 moneda de la compañía = 0,5 VSF → 1 VSF = 2
        })
        cls.lista = cls.env["product.pricelist"].create({
            "name": "Lista valor sin facturar",
            "currency_id": cls.moneda.id,
        })

    def _pedido(self, cantidad=10.0, precio=100.0, uom=None, descuento=0.0,
                lista=None, entregado=None):
        """Pedido confirmado de una línea, con su remito ya sellado."""
        pedido = self.env["sale.order"].create({
            "partner_id": self.cliente.id,
            "pricelist_id": (lista or self.lista).id,
            "order_line": [(0, 0, {
                "product_id": self.producto.id,
                "product_uom_qty": cantidad,
                "product_uom": (uom or self.unidad).id,
                "price_unit": precio,
                "discount": descuento,
            })],
        })
        pedido.action_confirm()
        remito = pedido.picking_ids[:1]
        self.assertTrue(remito, "El pedido confirmado tiene que haber creado la entrega")
        for move in remito.move_ids:
            move.quantity = entregado if entregado is not None else cantidad
        # El sello es lo que mete al remito en el circuito del indicador: sin él el
        # estado queda vacío y no hay nada que valorizar.
        remito.guvens_remito_number = "VSF-%s" % pedido.id
        return pedido, remito

    # ---------------- el cálculo ----------------
    def test_valor_es_cantidad_por_precio(self):
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        self.assertEqual(remito.guvens_plazo_estado, "pendiente")
        self.assertEqual(remito.guvens_valor_sin_facturar, 1000.0)
        self.assertEqual(remito.guvens_valor_moneda_id, self.moneda)

    def test_el_descuento_se_aplica(self):
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0, descuento=25.0)
        self.assertEqual(remito.guvens_valor_sin_facturar, 750.0)

    def test_la_unidad_de_medida_se_convierte(self):
        """El precio es por docena y la cantidad del movimiento viene en unidades.

        Sin conversión el valor saldría doce veces más chico: es el error que no
        avisa, porque el número igual queda redondo y el conteo de remitos cuadra.
        """
        _pedido, remito = self._pedido(cantidad=2.0, precio=120.0, uom=self.docena)
        for move in remito.move_ids:
            self.assertEqual(move.product_uom, self.unidad,
                             "El movimiento tiene que quedar en la unidad del producto")
            move.quantity = 24.0  # dos docenas, expresadas en unidades
        self.assertEqual(remito.guvens_valor_sin_facturar, 240.0)

    def test_un_movimiento_sin_linea_no_suma_y_marca_el_remito(self):
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        self.env["stock.move"].create({
            "name": "Movimiento suelto",
            "picking_id": remito.id,
            "product_id": self.producto.id,
            "product_uom_qty": 5.0,
            "quantity": 5.0,
            "product_uom": self.unidad.id,
            "location_id": remito.location_id.id,
            "location_dest_id": remito.location_dest_id.id,
        })
        self.assertEqual(remito.guvens_valor_sin_facturar, 1000.0,
                         "El renglón sin precio no debe sumar nada")
        self.assertTrue(remito.guvens_valor_incompleto,
                        "Y el remito tiene que quedar marcado para revisarlo")

    def test_se_convierte_a_la_moneda_de_la_compania(self):
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        self.assertEqual(remito.guvens_valor_sin_facturar_ars, 2000.0)
        self.assertEqual(remito.guvens_company_currency_id, self.env.company.currency_id)

    def test_sin_sello_no_se_valoriza(self):
        """Mientras no se cargue el número del talonario el remito no entra."""
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        remito.guvens_remito_number = False
        self.assertFalse(remito.guvens_plazo_estado)
        self.assertEqual(remito.guvens_valor_sin_facturar, 0.0)
        self.assertEqual(remito.guvens_valor_sin_facturar_ars, 0.0)

    def test_el_marcado_como_no_se_factura_tambien_se_valoriza(self):
        """Es el caso que pidió Franco: no va a tener comprobante y el saldo existe."""
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        remito.guvens_motivo_no_facturado = "sin_factura"
        self.assertEqual(remito.guvens_plazo_estado, "no_factura")
        self.assertEqual(remito.guvens_valor_sin_facturar, 1000.0)

    def test_sin_cantidad_cargada_se_usa_la_demanda(self):
        """El remito se imprime sin validar el albarán: ahí `quantity` está en cero.

        Es el caso normal en Sur Técnica, no la excepción. Medido en testing el
        21/10/2026, 6 de los 26 remitos sin facturar con una sola entrega quedaban en
        $0 por esto —uno de ellos de $342.831,31— aunque la mercadería había salido.
        """
        _pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        for move in remito.move_ids:
            move.quantity = 0.0
            self.assertEqual(move.product_uom_qty, 10.0)
        self.assertEqual(remito.guvens_valor_sin_facturar, 1000.0)

    def test_el_descuento_no_arrastra_el_redondeo_del_unitario(self):
        """60 a 18,35 con 18% son 902,82, no 903,00.

        El unitario con descuento es 15,047: redondeado a 15,05 y multiplicado por 60
        da 18 centavos de más. Por eso el precio sale del subtotal y no del unitario.
        Es el caso real del remito WH/OUT/02804.
        """
        pedido, remito = self._pedido(cantidad=60.0, precio=18.35, descuento=18.0)
        self.assertEqual(remito.guvens_valor_sin_facturar, pedido.amount_untaxed)
        self.assertNotEqual(remito.guvens_valor_sin_facturar, 903.00)

    # ---------------- control contra el pedido ----------------
    def test_con_un_solo_remito_coincide_con_el_neto_del_pedido(self):
        """La prueba de que el cálculo está bien, con la comparación correcta.

        Contra `amount_untaxed` y NO contra `amount_to_invoice`: ese segundo campo
        viene con impuestos incluidos. Medido en testing el 21/10/2026, el pedido
        S06506 de Palmar tiene neto 3.000 y `amount_to_invoice` 3.630 —el 21% de
        IVA—, así que compararlo contra el valor sin impuestos daría una diferencia
        que no es un error del cálculo.
        """
        pedido, remito = self._pedido(cantidad=10.0, precio=100.0)
        self.assertEqual(len(pedido.picking_ids), 1)
        self.assertEqual(remito.guvens_valor_sin_facturar, pedido.amount_untaxed)
