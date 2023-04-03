# Copyright (C) 2009  Renato Lima - Akretion
# Copyright (C) 2012  Raphaël Valyi - Akretion
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from functools import partial

from odoo import api, fields, models
from odoo.tools import float_is_zero
from odoo.tools.misc import formatLang
from collections import defaultdict

from ...l10n_br_fiscal.constants.fiscal import (
    CFOP_DESTINATION_EXPORT,
    FISCAL_IN
)


# class AccountMove(models.Model):
#     _inherit = "account.move"
class AccountMove(models.Model):
    _name = "account.move"
    _inherit = [
        _name,
        "l10n_br_fiscal.document.mixin.methods",
        "l10n_br_fiscal.document.invoice.mixin",
    ]
    _inherits = {"l10n_br_fiscal.document": "fiscal_document_id"}
    _order = "date DESC, name DESC"
    amount_icms_relief_value = fields.Monetary(
        inverse="_inverse_amount_icms_relief",
        compute="_compute_amount",
        store=True,
    )

    # necessario para mostrar o campo total corretamente incluido frete, outros e seguros
    @api.depends('amount_icms_relief_value')
    def _inverse_amount_icms_relief(self):
        if len(self) > 1:
            return
        if self.move_type not in ('in_invoice','out_invoice'):
            return
        for move in self:
            if move.payment_state == 'invoicing_legacy':
                move.payment_state = move.payment_state
                continue
            for line in move.line_ids:
                if line.name in ["[DESONERACAO]"]:
                    move.with_context(
                        check_move_validity=False,
                        skip_account_move_synchronization=True,
                        force_delete=True,
                    ).write(
                        {
                            "line_ids": [(2, line.id)],
                            "to_check": False,
                        }
                    )
            for line in move.line_ids:
                if not line.exclude_from_invoice_tab and line.icms_relief_value > 0:
                    if line.icms_relief_value:
                        new_line = self.env["account.move.line"].new(
                            {
                                "name": "[DESONERACAO]",
                                "account_id": line.account_id.id,
                                "move_id": self.id,
                                "exclude_from_invoice_tab": True,
                                "price_unit": -line.icms_relief_value,
                            }
                        )
                    move.line_ids += new_line
                    move.with_context(check_move_validity=False)._onchange_currency()

    @api.depends(
        'line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
        'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state',
        'line_ids.full_reconcile_id',
        'line_ids.icms_relief_value'
    )
    def _compute_amount(self):
        result = super()._compute_amount()
        if len(self) > 1:
            return result
        for move in self:
            if move.payment_state == 'invoicing_legacy':
                # invoicing_legacy state is set via SQL when setting setting field
                # invoicing_switch_threshold (defined in account_accountant).
                # The only way of going out of this state is through this setting,
                # so we don't recompute it here.
                move.payment_state = move.payment_state
                continue
            total = 0.0
            total_currency = 0.0
            total_other = 0.0
            currencies = move._get_lines_onchange_currency().currency_id

            for line in move.line_ids:
                
                if move.is_invoice(include_receipts=True):
                    # === Invoices ===
                    total_other += line.freight_value + line.insurance_value + line.other_value
                    if not line.exclude_from_invoice_tab:
                        # Untaxed amount.
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.tax_line_id:
                        # Tax amount.
                        total += line.balance
                        total_currency += line.amount_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            if move.move_type == 'entry' or move.is_outbound():
                sign = 1
            else:
                sign = -1
            move.amount_total = sign * (total_currency if len(currencies) == 1 else total)
            if total_other:
                total += total_other
                move.amount_total = sign * (total)
                move.amount_total_signed = abs(total) if move.move_type == 'entry' else -total
                if move.move_type == 'entry':
                    move.amount_untaxed_signed = move.amount_untaxed_signed + total_other
                else:
                    move.amount_untaxed_signed = move.amount_untaxed_signed - total_other
        return result
