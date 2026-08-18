def post_init_hook(env):
    """Deja el menú completo a todos los usuarios internos que ya existían.

    Este módulo ata los menús generales de Odoo al grupo "Menú completo". Sin este
    paso, al instalar, todos los usuarios internos perderían de golpe apps que hoy
    usan. Acotar la pantalla de una persona es después un acto explícito: se le
    desmarca el grupo desde su usuario, y se revierte marcándolo de nuevo.

    Los usuarios que se creen más adelante NO reciben el grupo automáticamente, así
    que hay que marcárselo al darlos de alta si tienen que ver el sistema completo.
    """
    grupo = env.ref("surtecnica_remito.group_menu_completo")
    internos = env["res.users"].search([("share", "=", False), ("active", "=", True)])
    if internos:
        grupo.sudo().write({"users": [(4, usuario.id) for usuario in internos]})
