# -*- coding: utf-8 -*-
###############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2017 Humanytek (<www.humanytek.com>).
#    Rubén Bravo <rubenred18@gmail.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

from collections import defaultdict, namedtuple
from math import log10

from odoo import api, fields, models, _
from odoo.tools.date_utils import add, subtract
from odoo.tools.float_utils import float_round
from odoo.osv.expression import OR, AND
from collections import OrderedDict


class MrpProductionSchedule(models.Model):
    _inherit = 'mrp.production.schedule'
    _name = 'mrp.production.schedule'

    # product_compromise = fields.Float('Compromise qty', default=100.0)
    # outgoing_product = fields.Float('Outgoing qty', default=50.0)
    # incoming_product = fields.Float('Incoming qty', default=10.0)

    def get_production_schedule_view_state(self):
        res = super(MrpProductionSchedule, self).get_production_schedule_view_state()
        if res:
            for r in res:
                product_id = r['product_id'][0]
                location_dest_id = r['warehouse_id'][0]
                index = 0
                for forecast_id in r['forecast_ids']:
                    # Get incoming product qty
                    incoming_product = 0
                    domain = [
                        ('location_dest_id', 'child_of', location_dest_id),
                        ('location_id', '=', 4),
                        ('product_id', '=', product_id),
                        ('state', 'not in', ('cancel', 'draft', 'done')),
                        ('date_deadline', '>=', forecast_id['date_start']),
                        ('date_deadline', '<=', forecast_id['date_stop'])]
                    move_ids = self.env['stock.move'].search(domain, order='date_deadline')
                    if move_ids:
                        incoming_product = sum(move.product_uom_qty for move in move_ids)
                    r['forecast_ids'][index]['incoming_product'] = incoming_product

                    # Get product compromise qty
                    product_compromise_qty = 0
                    compromise_ids = self.env['product.compromise'].search([
                        ('stock_move_in_id.product_id', '=', product_id),
                        ('stock_move_in_id.date_deadline', '>=', forecast_id['date_start']),
                        ('stock_move_in_id.date_deadline', '<=', forecast_id['date_stop']),
                        ('stock_move_in_id.state', '=', 'assigned')
                    ])
                    if compromise_ids:
                        product_compromise_qty = sum(
                            compromise_id.qty_compromise for compromise_id in compromise_ids)
                    r['forecast_ids'][index]['product_compromise_qty'] = product_compromise_qty

                    # Get product reserve qty
                    product_reserve_qty = 0
                    stock_move_obj = self.env['stock.move']
                    default_location = self.env['stock.location'].search(
                        [('default_location', '=', 'True')], limit=1)
                    stock_moves = stock_move_obj.search(
                        [('product_id.id', '=', product_id),
                         ('state', 'in', ['assigned', 'confirmed', 'partially_available']),
                         ('location_id', '=', default_location.id),
                         ('date_deadline', '>=', forecast_id['date_start']),
                         ('date_deadline', '<=', forecast_id['date_stop'])])
                    product_reserve_qty = sum([move.reserved_availability
                                               for move in stock_moves])
                    r['forecast_ids'][index]['product_reserve_qty'] = product_reserve_qty
                    init_qty = r['forecast_ids'][index]['starting_inventory_qty'] + \
                        incoming_product - product_compromise_qty - \
                        product_reserve_qty - \
                        r['forecast_ids'][index]['replenish_qty'] - \
                        r['forecast_ids'][index]['outgoing_qty']
                    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> ", init_qty)
                    if index <= 10:
                        r['forecast_ids'][index+1]['starting_inventory_qty'] = init_qty
                    index += 1
            # print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  ", res)
        return res
