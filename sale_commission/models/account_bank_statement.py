from odoo import api, fields, models, _


class AccountBankStatementLine(models.Model):
    _name = "account.bank.statement.line"
    _inherit = "account.bank.statement.line"
    _description = "Bank Statement Line"

    def button_undo_reconciliation(self):
        for line in self.line_ids:
            reconcile_line_id = self.env['account.move.line'].search(
                [('id', 'in', line.move_id.line_ids._reconciled_lines()), ('move_id.move_type', '=', 'out_invoice')], limit=1)
            payment_line_id = self.env['account.move.line'].search(
                [('id', 'in', line.move_id.line_ids._reconciled_lines()), ('move_id.move_type', '!=', 'out_invoice')], limit=1)
            assoc = self.env['account.association'].search([
                ('move_line_id', '=', reconcile_line_id.id),
                ('payment_amount', '=', payment_line_id.credit)], limit=1)
            assoc.unlink()
            break
        super(AccountBankStatementLine, self).button_undo_reconciliation()
        # self.line_ids.remove_move_reconcile()
        # self.payment_ids.unlink()
        #
        # for st_line in self:
        #     st_line.with_context(force_delete=True).write({
        #         'to_check': False,
        #         'line_ids': [(5, 0)] + [(0, 0, line_vals) for line_vals in st_line._prepare_move_line_default_vals()],
        #     })
