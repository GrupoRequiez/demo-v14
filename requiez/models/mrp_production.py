# Copyright 2016 Antiun Ingenieria S.L. - Javier Iniesta
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _


class MrpProduction(models.Model):
    _inherit = "mrp.production"
    _name = "mrp.production"
    _description = ""

    order_classification = fields.Selection([
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D')],
        string="Order",
        default="A")
