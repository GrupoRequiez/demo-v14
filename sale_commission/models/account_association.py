# Copyright 2018 Vauxoo (https://www.vauxoo.com) <info@vauxoo.com>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class AccountAssociation(models.Model):
    _name = 'account.association'
    _description = 'account.association'

    move_id = fields.Many2one('account.move', ondelete='cascade',
                              help="Invoice")
    move_line_id = fields.Many2one(
        'account.move.line', ondelete='cascade',
        help="Move where the payment was registered")
    date = fields.Datetime(
        help="Date where the payment was registered in the system by the user")
    payment_amount = fields.Float(
        readonly=True, store=True,
        # compute='_compute_payment_amount',
        help="amount of the payment for this invoice")

    # Performance fields
    # This fields help us to avoid monster queries when the report is generated
    aml_state = fields.Selection(
        related='move_id.state', readonly=True, store=True)
    aml_invoice_type = fields.Selection(
        related='move_id.move_type', readonly=True, store=True)
