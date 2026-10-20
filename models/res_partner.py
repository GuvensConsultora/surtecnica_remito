from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    guvens_requiere_hes = fields.Boolean(
        string="Requiere HES para facturar",
        default=False,
        help="Clientes que, después de recibir la mercadería, emiten un código de "
             "conformidad (HES) sin el cual rechazan la factura.\n\n"
             "Marcarlo cambia dos cosas: a esos remitos no se les reclama el plazo de "
             "facturación, porque el momento de facturar no depende de Sur Técnica, y "
             "en el indicador se miden aparte de los demás.\n\n"
             "Nace desmarcado y lo carga administración cliente por cliente: no hay "
             "forma de deducir del sistema quién lo exige.",
    )
