# Copyright 2017 Humanytek.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from odoo import models
_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _name = "stock.move"
    _inherit = ['stock.move', 'sale.order.observation']

    def _compute_observation(self):
        for move in self:
            move.sale_line_observation = move.sale_line_id.observation


class StockMoveLine(models.Model):
    _name = "stock.move.line"
    _inherit = "stock.move.line"

    def _get_aggregated_product_quantities(self, **kwargs):
        """ Returns a dictionary of products (key = id+name+description+uom) and corresponding values of interest.

        Allows aggregation of data across separate move lines for the same product. This is expected to be useful
        in things such as delivery reports. Dict key is made as a combination of values we expect to want to group
        the products by (i.e. so data is not lost). This function purposely ignores lots/SNs because these are
        expected to already be properly grouped by line.

        returns: dictionary {product_id+name+description+uom: {product, name, description, qty_done, product_uom}, ...}
        """
        aggregated_move_lines = {}
        for move_line in self:
            name = move_line.product_id.display_name
            description = move_line.move_id.description_picking
            if description == name or description == move_line.product_id.name:
                description = False
            uom = move_line.product_uom_id
            line_key = str(move_line.product_id.id) + "_" + name + \
                (description or "") + "uom " + str(uom.id)

            if line_key not in aggregated_move_lines:
                aggregated_move_lines[line_key] = {'name': name,
                                                   'description': description,
                                                   'qty_done': move_line.qty_done,
                                                   'product_uom': uom.name,
                                                   'product': move_line.product_id,
                                                   'sale_line_observation': move_line.move_id.sale_line_id.observation}
            else:
                aggregated_move_lines[line_key]['qty_done'] += move_line.qty_done
        return aggregated_move_lines
