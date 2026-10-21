from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    guvens_plazo_facturacion_dias = fields.Integer(
        string="Plazo para facturar un remito (días hábiles)",
        help="Días hábiles que pueden pasar entre que se confecciona el remito y se "
             "emite la factura. El indicador marca como excedidos los que lo superan.\n\n"
             "Nace vacío a propósito: mientras no se cargue, el sistema mide los días "
             "igual pero no marca a nadie como excedido. El plazo lo fija la empresa, "
             "no nosotros.\n\n"
             "Los días se cuentan con el calendario laboral de la compañía, así que "
             "sábados y domingos no suman. Los feriados tampoco, siempre que estén "
             "cargados en ese calendario.",
    )

    guvens_aviso_facturacion_user_id = fields.Many2one(
        "res.users",
        string="Avisar a",
        domain=[("share", "=", False)],
        help="Persona que recibe el aviso cuando se confecciona un remito, para que "
             "emita la factura. Le aparece como una actividad pendiente, con "
             "vencimiento según el plazo de más arriba.\n\n"
             "Nace vacío y mientras lo esté no se avisa a nadie. Conviene apuntarlo "
             "al usuario con el que trabaja quien factura: si es una cuenta "
             "compartida, el aviso llega a esa bandeja y no a una persona.\n\n"
             "A los clientes que exigen HES no se les avisa: ahí el momento de "
             "facturar no depende de Sur Técnica.",
    )

    def write(self, vals):
        """Recalcula el estado de los remitos cuando cambia el plazo.

        El recálculo se dispara a mano, acotado a los remitos que tienen sello, en
        vez de poner el campo de la compañía en el `@api.depends` del albarán: ahí
        Odoo marcaría para recomputar TODOS los albaranes de la compañía —decenas
        de miles— cada vez que alguien guarda la ficha. Los remitos con sello son
        unos cientos.
        """
        resultado = super().write(vals)
        if "guvens_plazo_facturacion_dias" in vals:
            remitos = self.env["stock.picking"].search([
                ("company_id", "in", self.ids),
                ("guvens_remito_fecha", "!=", False),
            ])
            if remitos:
                remitos.modified(["guvens_remito_fecha"])
        return resultado
