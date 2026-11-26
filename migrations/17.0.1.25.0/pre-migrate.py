"""Crea las columnas del indicador de cumplimiento antes de que Odoo las cree.

Si Odoo crea un campo computado almacenado nuevo, lo calcula sobre TODOS los
albaranes y les mueve la fecha de modificación. Con la columna ya creada no lo hace:
el cálculo se acota en el post-migrate a los remitos que tienen fecha de confección.
"""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE stock_picking
            ADD COLUMN IF NOT EXISTS guvens_cumplimiento varchar,
            ADD COLUMN IF NOT EXISTS guvens_en_tiempo integer,
            ADD COLUMN IF NOT EXISTS guvens_fuera_plazo integer,
            ADD COLUMN IF NOT EXISTS guvens_cumplimiento_pct double precision
    """)
