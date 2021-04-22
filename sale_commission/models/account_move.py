# Copyright 2018 Vauxoo (https://www.vauxoo.com) <info@vauxoo.com>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = "account.move"
    _description = "Journal Entry"

    def js_assign_outstanding_line(self, line_id):
        res = super(AccountMove, self).js_assign_outstanding_line(line_id)
        for apr_id in res['partials']:
            self.env['account.association'].create({
                'move_id': apr_id.debit_move_id.move_id.id,
                'move_line_id': apr_id.debit_move_id.id,
                'payment_amount': apr_id.amount,
                'date': fields.Datetime.now()
            })
        return res

    def js_remove_outstanding_partial(self, partial_id):
        self.ensure_one()
        partial = self.env['account.partial.reconcile'].browse(partial_id)
        for line_id in partial.debit_move_id:
            assoc = self.env['account.association'].search([
                ('move_line_id', '=', line_id.id),
                ('payment_amount', '=', partial.amount)], limit=1)
            assoc.unlink()
        return partial.unlink()

    association_ids = fields.One2many('account.association', 'move_id',
                                      string="Associations")
