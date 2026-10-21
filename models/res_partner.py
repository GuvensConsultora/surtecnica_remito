from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    guvens_requiere_hes = fields.Boolean(
        string="Requiere HES para facturar",
        default=False,
        help="Clientes que, después de recibir la mercadería, emiten un código de "
             "conformidad (HES) sin el cual rechazan la factura, o que tienen que "
             "autorizar antes de que se pueda facturar.\n\n"
             "Marcarlo acá no decide nada por sí solo: hace que los remitos de ese "
             "cliente NAZCAN con el tilde «Requiere HES / autorización» marcado. El "
             "tilde del remito se puede destildar cuando esa entrega puntual no la "
             "lleve, y es el tilde —no esta lista— el que define si se le reclama el "
             "plazo de facturación.\n\n"
             "Marcarlo o desmarcarlo no mueve los remitos ya confeccionados, para no "
             "pisar una decisión que alguien ya tomó a mano.\n\n"
             "Nace desmarcado y lo carga administración cliente por cliente: no hay "
             "forma de deducir del sistema quién lo exige.",
    )
