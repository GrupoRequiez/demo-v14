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

import datetime
from dateutil import relativedelta
import babel.dates
import pytz

from odoo import api, fields, models, _
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT


NUMBER_OF_COLS = 12


class MrpMpsReport(models.TransientModel):
    _name = 'mrp.mps.report'
    _description = 'MPS Report'

    def _default_manufacturing_period(self):
        return self.env.user.company_id.manufacturing_period

    company_id = fields.Many2one('res.company', string="Company",
                                 default=lambda self: self.env['res.company']._company_default_get('mrp.mps.report'), required=True)
    period = fields.Selection([('month', 'Monthly'), ('week', 'Weekly'), (
        'day', 'Daily')], default=_default_manufacturing_period, string="Period")
    # TODO: this object should not be used as wizard and as report
    product_id = fields.Many2one('product.product', string='Product')

    def add_product_mps(self):
        MrpBomLine = self.env['mrp.bom.line']
        for mps in self:
            mps.product_id.write({
                'mps_active': True,
                'apply_active': self.env['mrp.bom']._bom_find(product=mps.product_id, company_id=mps.company_id.id) and True or False})
            # If you add a difference account
            boms = MrpBomLine.search(
                [('product_id', '=', mps.product_id.id)]).mapped('bom_id')
            for bom in boms:
                products = (bom.product_id or (
                    bom.product_tmpl_id.product_variant_ids)).filtered(lambda x: x.mps_active)
                if products:
                    products.apply_active = True
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def get_indirect(self, product, date=False, date_to=False):
        domain = [('product_id', '=', product.id)]
        data = self.env['sale.forecast.indirect'].search(domain)
        result = {product.id: {}}
        for d in data:
            result.setdefault(d.product_id.id, {})
            result[d.product_id.id].setdefault(d.date, 0.0)
            result[d.product_id.id][d.date] += d.quantity
        return result

    @api.model
    def _set_indirect(self, product, data):
        self.env['sale.forecast.indirect'].search(
            [('product_origin_id', '=', product.id)]).unlink()
        BoM = self.env['mrp.bom']
        #products_to_calculate = [(product, datas),]

        products_to_calculate = {product: []}
        for inner_data in data:
            products_to_calculate[product].append({'lead': 0.0,
                                                   'qty': inner_data['to_supply'],
                                                   'date': fields.Date.from_string(inner_data['date']),
                                                   })
        original_product = product
        while products_to_calculate:
            (product, product_lines) = products_to_calculate.popitem()
            # TODO: how is it possible not to find a BoM here?
            bom = BoM._bom_find(product=product)
            if not bom:
                break
            # TODO: Take into account security days on company level
            product_qty = bom.product_uom_id._compute_quantity(
                bom.product_qty, product.uom_id)
            explored_boms, explored_lines = bom.explode(
                product, 1.0 / product_qty)
            for bom_line, line_data in explored_lines:

                # If the product is in the report, add it to the objects of the report immediately,
                # else search further and add to products_to_calculate if you find something
                if bom_line.product_id.mps_active:
                    for supply_line in product_lines:
                        lead = product.produce_delay + supply_line['lead']
                        qty = bom_line.product_uom_id._compute_quantity(
                            line_data['qty'], bom_line.product_id.uom_id)
                        self.env['sale.forecast.indirect'].create({
                            'product_origin_id': original_product.id,
                            'product_id': bom_line.product_id.id,
                            'quantity': qty * supply_line['qty'],
                            'date': supply_line['date'] - relativedelta.relativedelta(days=product.produce_delay)
                            # The date the product is needed (don't calculate its own lead time)
                        })
                    if BoM._bom_find(product=bom_line.product_id):
                        bom_line.product_id.apply_active = True
                else:
                    # If there is a child BoM, add them to the dictionary
                    bom = BoM._bom_find(product=bom_line.product_id)
                    if bom:
                        products_to_calculate.setdefault(
                            bom_line.product_id, [])
                        qty = bom_line.product_uom_id._compute_quantity(
                            line_data['qty'], bom_line.product_id.uom_id)
                        for supply_line in product_lines:
                            lead = supply_line['lead'] + \
                                bom_line.product_id.produce_delay
                            products_to_calculate[bom_line.product_id].append({
                                'lead': lead,
                                'qty': qty * supply_line['qty'],
                                'date': supply_line['date'] - relativedelta.relativedelta(days=product.produce_delay),
                            })
        return True

    @api.model
    def update_indirect(self, product):
        forcast = self.search([])[0]
        if isinstance(product, int):
            product = self.env['product.product'].browse(product)
        product.apply_active = False
        datas = forcast.get_data(product)
        self._set_indirect(product, datas)
        return True

    def get_data(self, product):
        """Getting data considering the quantity available"""
        # pylint: disable=C0103
        StockMove = self.env['stock.move']
        MrpMpsLocation = self.env['mrp.mps.location']
        ProductCompromise = self.env['product.compromise']
        StockWarehouseOrderpoint = self.env['stock.warehouse.orderpoint']
        result = []
        forecasted = product.mps_forecasted
        date = datetime.datetime.now()
        indirect = self.get_indirect(product)[product.id]
        display = _('To Supply / Produce')
        buy_type = self.env.ref(
            'purchase_stock.route_warehouse0_buy', raise_if_not_found=False)
        mo_type = self.env.ref(
            'mrp.route_warehouse0_manufacture', raise_if_not_found=False)
        lead_time = 0
        routes = product.route_ids.ids
        if buy_type.id in routes:
            lead_time = (
                product.seller_ids and product.seller_ids[0].delay or 0) + self.env.user.company_id.po_lead
        lead_time = (product.produce_delay +
                     self.env.user.company_id.manufacturing_lead) if mo_type and mo_type.id in routes else lead_time
        leadtime = date + relativedelta.relativedelta(days=int(lead_time))
        # Take first day of month or week
        date_dict = {
            'month': lambda d: datetime.datetime(d.year, d.month, 1),
            'week': lambda d: d - relativedelta.relativedelta(days=d.weekday())
        }
        date = date_dict.get(self.period, lambda d: d)(date)
        mrp_mps_locations = MrpMpsLocation.search([])
        location_ids = []
        list_location = []
        len_location = len(mrp_mps_locations)
        cont = 1
        for mrp_mps_location in mrp_mps_locations:
            location_ids.append(mrp_mps_location.location_id.id)
            tuple_location = ('location_id', 'child_of',
                              mrp_mps_location.location_id.id)
            if cont < len_location:
                list_location.append('|')
            list_location.append(tuple_location)
            cont += 1

        initial = 0.0
        stock_quats_ids = self.env['stock.quant'].search(
            [('product_id', '=', product.id), ('quantity', '>', 0.0), ('location_id', 'in', (location_ids))])

        initial += sum([c.quantity for c in stock_quats_ids])

        # initial = product.qty_available
        # Compute others cells

        # Better perfomance
        date_to_full = date + relativedelta.relativedelta(days=1)
        if self.period == 'month':
            date_to_full = date + \
                relativedelta.relativedelta(months=1 * NUMBER_OF_COLS)
        elif self.period == 'week':
            date_to_full = date + \
                relativedelta.relativedelta(days=7 * NUMBER_OF_COLS)
        domain2_full = [
            ('raw_material_production_id.sale_id.date_promised',
             '>=', date.strftime('%Y-%m-%d')),
            ('raw_material_production_id.sale_id.date_promised',
             '<', date_to_full.strftime('%Y-%m-%d')),
            ('state', 'not in', ['cancel', 'done']),
            ('product_id.id', '=', product.id)
        ]
        stock_move_outs_full = StockMove.search(domain2_full)
        stock_warehouse = StockWarehouseOrderpoint.search(
            [('product_id.id', '=', product.id)])
        # END of Better performance
        for col in range(NUMBER_OF_COLS):
            date_to = date + relativedelta.relativedelta(days=1)
            name = babel.dates.format_date(
                format="MMM d", date=date, locale=self._context.get('lang') or 'en_US')
            if self.period == 'month':
                date_to = date + relativedelta.relativedelta(months=1)
                name = date.strftime('%b')
                name = babel.dates.format_date(
                    format="MMM YY", date=date, locale=self._context.get('lang') or 'en_US')
            elif self.period == 'week':
                date_to = date + relativedelta.relativedelta(days=7)
                name = _('Week %s') % date.isocalendar()[1]
            forecasts = self.env['sale.forecast'].search([  # TODO Check
                ('date', '>=', date.strftime('%Y-%m-%d')),
                ('date', '<', date_to.strftime('%Y-%m-%d')),
                ('product_id', '=', product.id),
            ])
            state = 'draft'
            mode = 'auto'
            proc_dec = False
            demand = 0.0
            for fore in forecasts:
                mode = 'manual' if fore.mode == 'manual' else mode
                state = 'done' if fore.state == 'done' else 'draft'
                demand += (fore.forecast_qty if fore.mode == 'auto' else 0)
            proc_dec = state == 'done'

            indirect_total = sum([qty for day, qty in indirect.items(
            ) if date <= datetime.datetime.combine(day, datetime.datetime.min.time()) < date_to])
            to_supply = (product.mps_forecasted -
                         initial + demand + indirect_total)
            to_supply = max(to_supply, product.mps_min_supply)
            to_supply = min(
                product.mps_max_supply, to_supply) if product.mps_max_supply > 0 else to_supply

            qty_in = 0
            product_in = 0
            compromise_qty = 0
            point = 0
            calc = 0
            product_out = 0
            compromise_out_qty = 0
            if buy_type.id in routes:
                domain = [  # TODO Check
                    ('date_expected', '>=', date.strftime('%Y-%m-%d')),
                    ('date_expected', '<', date_to.strftime('%Y-%m-%d')),
                    ('picking_type_id.code', '=', 'incoming'),
                    ('state', 'not in', ['cancel', 'done']),
                    ('product_id.id', '=', product.id),
                ]
                stock_moves = StockMove.search(domain)
                for move in stock_moves:
                    product_in += move.product_uom_qty
                    product_compromise = ProductCompromise.search([
                        ('stock_move_in_id.id', '=', move.id),
                        ('state', '=', 'assigned'),
                    ])
                    for compromise in product_compromise:
                        compromise_qty += compromise.qty_compromise

                # domain2 = [
                #     ('raw_material_production_id.sale_id.date_promised', '>=', date.strftime('%Y-%m-%d')),
                #     ('raw_material_production_id.sale_id.date_promised', '<', date_to.strftime('%Y-%m-%d')),
                #     ('state', 'not in', ['cancel', 'done']),
                #     ('product_id.id', '=', product.id)
                # ]
                # stock_move_outs = StockMove.search(domain2)
                date_to_str = date_to.strftime('%Y-%m-%d')
                date_str = date.strftime('%Y-%m-%d')
                stock_move_outs = stock_move_outs_full.filtered(lambda r: r.raw_material_production_id.sale_id.date_promised >= date
                                                                and
                                                                r.raw_material_production_id.sale_id.date_promised < date_to)
                for move_out in stock_move_outs:
                    product_out += move_out.product_uom_qty
                    product_out_compromise = ProductCompromise.search([
                        ('stock_move_out_id.id', '=', move_out.id),
                        ('state', '=', 'assigned'),
                    ])
                    compromise_out_qty += sum(
                        [c.qty_compromise for c in product_out_compromise])

                if self.period == 'day' or self.period == 'week' and col == 0:
                    date_old = datetime.datetime(date.year, date.month, 1)
                    domain3 = [  # TODO Check
                        ('raw_material_production_id.sale_id.date_promised',
                         '>=', date_old.strftime('%Y-%m-%d')),
                        ('raw_material_production_id.sale_id.date_promised',
                         '<', date.strftime('%Y-%m-%d')),
                        ('state', 'not in', ['cancel', 'done']),
                        ('product_id.id', '=', product.id),
                    ]
                    stock_move_outs = StockMove.search(domain3)
                    for move_out in stock_move_outs:
                        product_out += move_out.product_uom_qty
                        product_out_compromise = ProductCompromise.search(
                            [('stock_move_out_id.id', '=', move_out.id)])
                        compromise_out_qty += sum(
                            [c.qty_compromise for c in product_out_compromise])
            prod_in = 0

            product_in_forecasted = qty_in if qty_in > 0 else 0
            prod_in = qty_in > 0
            point = stock_warehouse.product_min_qty

            fore = (initial - point) if product_in_forecasted > 0 else 0
            product_in_forecasted = 0 if fore >= 0 else abs(fore)

            product_out -= compromise_out_qty
            forecasted = (product_in_forecasted - demand +
                          initial - product_out + product_in - compromise_qty)

            calc = forecasted - point
            calc = abs(calc) if calc < 0 else 0

            to_supply = sum(forecasts.filtered(lambda x: x.mode == 'manual').mapped(
                'to_supply')) if mode == 'manual' else calc

            result.append({
                'period': name,
                'date': date.strftime('%Y-%m-%d'),
                'date_to': date_to.strftime('%Y-%m-%d'),
                'initial': initial,
                'product_in': product_in,
                'product_out': product_out,
                'compromise_qty': compromise_qty,
                'product_in_forecasted': product_in_forecasted,
                'in': prod_in,
                'demand': demand,
                'mode': mode,
                'state': state,
                'indirect': indirect_total,
                'to_supply': to_supply,
                'forecasted': forecasted,
                'route_type': display,
                'procurement_enable': not proc_dec and leadtime >= date,
                'procurement_done': proc_dec,
                'lead_time': leadtime.strftime('%Y-%m-%d'),
            })
            initial = forecasted
            date = date_to
        return result

    @api.model
    def get_html(self, domain=[]):
        res = self.search([], limit=1)
        if not res:
            res = self.create({})
        domain.append(['mps_active', '=', True])
        rcontext = {
            'products': [(x, res.get_data(x)) for x in self.env['product.product'].search(domain, limit=20)],
            'nb_periods': NUMBER_OF_COLS,
            'company': self.env.user.company_id,
            'format_float': self.env['ir.qweb.field.float'].value_to_html,
        }
        result = {
            'html': self.env.ref('requiez.report_inventory').render(rcontext),
            'report_context': {'nb_periods': NUMBER_OF_COLS, 'period': res.period},
        }
        return result


class MMpsLocation(models.Model):
    _name = "mrp.mps.location"

    location_id = fields.Many2one('stock.location', 'Location', required=True)
    active = fields.Boolean('Active', default=True)
