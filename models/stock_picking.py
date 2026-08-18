from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("guvens_remito_number"):
                vals["guvens_remito_number"] = vals["guvens_remito_number"].strip()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("guvens_remito_number"):
            vals["guvens_remito_number"] = vals["guvens_remito_number"].strip()
        return super().write(vals)

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
