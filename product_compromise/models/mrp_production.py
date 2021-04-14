# Copyright 2017 Humanytek.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from odoo import api, models
_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # @api.multi
    def action_assign(self):
        for production in self:
            move_to_assign = production.move_raw_ids.filtered(
                lambda x: x.state in (
                    'confirmed', 'waiting', 'assigned',
                    'partially_available'))
            if production.sale_id:
                move_to_assign.filtered(
                    lambda s: s.compromise_qty <= 0)._action_assign()
                return True
            move_to_assign._action_assign()
        return True

    def _action_cancel(self):
        if super(MrpProduction, self)._action_cancel():
            product_compromise = self.env['product.compromise']
            product_compromises = product_compromise.search([(
                'stock_move_out_id.state', '=', 'cancel')])
            product_compromises.unlink()
        return True
