from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRequiereHes(TransactionCase):
    """El campo de HES es un dato puro, sin lógica: lo que hay que proteger no es un
    cálculo sino la decisión de que nace vacío y lo carga administración.

    Quién exige HES no se puede deducir del sistema, así que cualquier valor que el
    módulo trajera puesto sería una suposición nuestra sobre el circuito del cliente.
    Y el costo de equivocarse no es simétrico: marcar de más silencia el plazo de un
    cliente al que sí había que reclamarle, y eso no se nota —el indicador simplemente
    deja de contarlo—.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env["res.partner"].create({"name": "Cliente de prueba HES"})

    def test_nace_desmarcado(self):
        """Un cliente nuevo no requiere HES hasta que alguien lo diga."""
        self.assertFalse(self.cliente.guvens_requiere_hes)

    def test_instalar_no_marca_a_nadie(self):
        """Instalar el módulo no debe dejar ningún cliente marcado.

        Es el control de que no entró una lista precargada por código ni por datos
        semilla: la carga es cliente por cliente y la hace administración.
        """
        marcados = self.env["res.partner"].search_count([
            ("guvens_requiere_hes", "=", True),
        ])
        self.assertEqual(
            marcados, 0,
            "Hay clientes marcados como 'requiere HES' sin que nadie los haya cargado.",
        )

    def test_se_puede_marcar_y_filtrar(self):
        """El campo tiene que estar almacenado: el indicador agrupa por él."""
        self.cliente.guvens_requiere_hes = True
        encontrados = self.env["res.partner"].search([
            ("guvens_requiere_hes", "=", True),
            ("id", "=", self.cliente.id),
        ])
        self.assertEqual(encontrados, self.cliente)

    def test_vale_igual_en_las_dos_companias(self):
        """El requisito lo impone el cliente, no nuestra razón social.

        Por eso el campo no es company_dependent: si lo fuera, marcarlo en una
        compañía dejaría al mismo cliente sin marcar en la otra y el indicador le
        reclamaría un plazo que no corresponde.
        """
        companias = self.env["res.company"].search([], limit=2)
        if len(companias) < 2:
            self.skipTest("La base tiene una sola compañía")
        self.cliente.guvens_requiere_hes = True
        otra = self.cliente.with_company(companias[1])
        self.assertTrue(otra.guvens_requiere_hes)
