"""Calcula el indicador de cumplimiento sólo en los remitos con fecha de confección."""
from odoo import api, SUPERUSER_ID

CAMPOS = ("guvens_cumplimiento", "guvens_en_tiempo", "guvens_fuera_plazo",
          "guvens_cumplimiento_pct")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Picking = env["stock.picking"]
    remitos = Picking.search([("guvens_remito_fecha", "!=", False)])
    if not remitos:
        return
    for nombre in CAMPOS:
        env.add_to_compute(Picking._fields[nombre], remitos)
    env.flush_all()
