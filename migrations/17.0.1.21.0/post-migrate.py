"""Recalcula el plazo y el valor sin facturar de los remitos con anticipos.

Desde 1.21.0 una factura que es sólo de anticipo no cuenta como factura del remito
(caso ERAMINE S06332). Los campos son almacenados y el deploy no los recalcula solo:
se recalculan acá, acotados a los remitos de pedidos con líneas de anticipo.
"""
from odoo import api, SUPERUSER_ID

CAMPOS = (
    "guvens_factura_id", "guvens_dias_a_factura", "guvens_plazo_estado",
    "guvens_dias_sin_facturar", "guvens_valor_moneda_id", "guvens_valor_sin_facturar",
    "guvens_valor_sin_facturar_ars", "guvens_valor_incompleto",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env["sale.order.line"].search([("is_downpayment", "=", True)]).order_id
    remitos = pedidos.picking_ids.filtered("guvens_remito_fecha")
    if not remitos:
        return
    Picking = env["stock.picking"]
    for nombre in CAMPOS:
        if nombre in Picking._fields:
            env.add_to_compute(Picking._fields[nombre], remitos)
    env.flush_all()
