from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        """Al postear una factura de cliente, cierra el aviso de sus remitos.

        Si no se cierra acá, en la bandeja de quien factura quedan actividades
        vencidas de remitos que ya se facturaron. Ese ruido es lo que hace que la
        gente deje de mirar las actividades, y entonces el aviso no sirve para nada.

        Se engancha en `_post` y no en el compute del plazo a propósito: crear o
        cerrar actividades desde un campo calculado las dispararía también en los
        recómputos masivos, que no son hechos del circuito.
        """
        posteadas = super()._post(soft=soft)
        facturas = posteadas.filtered(lambda m: m.move_type == "out_invoice")
        if facturas:
            pedidos = facturas.line_ids.sale_line_ids.order_id
            remitos = pedidos.picking_ids.filtered("guvens_remito_fecha")
            if remitos:
                remitos._guvens_cerrar_aviso_facturar()
        return posteadas
