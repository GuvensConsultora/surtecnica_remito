from odoo import api, models


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    def _guvens_remitos_a_recalcular(self):
        """Los remitos cuyo plazo puede haber cambiado por estas ausencias.

        El plazo se cuenta en días hábiles, así que cargar o borrar un feriado cambia
        los días de todo remito cuyo tramo remito→factura lo incluya. Los feriados no
        están en el `@api.depends` del cálculo a propósito: habría que escuchar a otro
        modelo entero, y Odoo marcaría para recomputar todos los albaranes cada vez
        que alguien registra la ausencia de un empleado.

        Por eso el recálculo se dispara a mano y acotado a los remitos CON SELLO —unos
        cientos, contra decenas de miles de albaranes—, y sólo de las compañías cuyo
        calendario cambió. Una ausencia sin calendario vale para todas, así que ahí no
        se acota.

        Es el mismo patrón que usa `res.company.write` para el plazo.
        """
        dominio = [("guvens_remito_fecha", "!=", False)]
        calendarios = self.mapped("calendar_id")
        if calendarios and all(ausencia.calendar_id for ausencia in self):
            companias = self.env["res.company"].search([
                ("resource_calendar_id", "in", calendarios.ids),
            ])
            dominio.append(("company_id", "in", companias.ids))
        return self.env["stock.picking"].search(dominio)

    def _guvens_recalcular_remitos(self):
        remitos = self._guvens_remitos_a_recalcular()
        if remitos:
            remitos.modified(["guvens_remito_fecha"])

    @api.model_create_multi
    def create(self, vals_list):
        ausencias = super().create(vals_list)
        ausencias._guvens_recalcular_remitos()
        return ausencias

    def write(self, vals):
        # Las dos puntas: si el feriado se mueve de fecha o de calendario, hay que
        # volver a medir los remitos de antes y los de después.
        self._guvens_recalcular_remitos()
        resultado = super().write(vals)
        self._guvens_recalcular_remitos()
        return resultado

    def unlink(self):
        # Los remitos se resuelven ANTES de borrar: después ya no se sabe a qué
        # calendario pertenecía la ausencia.
        remitos = self._guvens_remitos_a_recalcular()
        resultado = super().unlink()
        if remitos:
            remitos.modified(["guvens_remito_fecha"])
        return resultado
