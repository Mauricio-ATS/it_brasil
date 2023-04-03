# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import UserError


class AccountMoveReversal(models.TransientModel):
    """
    Account move reversal wizard, it cancel an account move by reversing it.
    """
    _inherit = 'account.move.reversal'

    def reverse_moves(self):
        self.ensure_one()
        moves = self.move_ids

        # Create default values.
        default_values_list = []
        for move in moves:
            default_values_list.append(self._prepare_default_reversal(move))

        batches = [
            [self.env['account.move'], [], True],   # Moves to be cancelled by the reverses.
            [self.env['account.move'], [], False],  # Others.
        ]
        for move, default_vals in zip(moves, default_values_list):
            is_auto_post = bool(default_vals.get('auto_post'))
            is_cancel_needed = not is_auto_post and self.refund_method in ('cancel', 'modify')
            batch_index = 0 if is_cancel_needed else 1
            batches[batch_index][0] |= move
            batches[batch_index][1].append(default_vals)
        
        # Handle reverse method.
        moves_to_redirect = self.env['account.move']
        for moves, default_values_list, is_cancel_needed in batches:
            new_moves = moves._reverse_moves(default_values_list, cancel=is_cancel_needed)

            if self.refund_method == 'modify':
                moves_vals_list = []
                for move in moves.with_context(include_business_fields=True):
                    moves_vals_list.append(move.copy_data({'date': self.date if self.date_mode == 'custom' else move.date})[0])
                new_moves = self.env['account.move'].create(moves_vals_list)

            moves_to_redirect |= new_moves

        self.new_move_ids = moves_to_redirect

        # Carlos ini
        # import pudb;pu.db
        for moves, default_values_list, is_cancel_needed in batches:
            numero_itens = len(moves.invoice_line_ids)
            while numero_itens > 0:
                for line in self.new_move_ids.invoice_line_ids:
                    mv = moves.invoice_line_ids[numero_itens-1]
                    if line.product_id.id == mv.product_id.id:
                        line.icms_tax_id = mv.icms_tax_id.id
                        line.icms_cst_id = mv.icms_cst_id.id
                        line.icms_origin = mv.icms_origin
                        line.icms_base_type = mv.icms_base_type
                        line.icms_base = mv.icms_base
                        line.icms_percent = mv.icms_percent
                        line.icms_value = mv.icms_value
                        line.icms_relief_id = mv.icms_relief_id
                        line.icms_relief_value = mv.icms_relief_value
                        line.icms_substitute = mv.icms_substitute
                        line.ipi_tax_id = mv.ipi_tax_id.id
                        line.ipi_guideline_id = mv.ipi_guideline_id.id
                        line.ipi_base_type = mv.ipi_base_type
                        line.ipi_percent = mv.ipi_percent
                        line.ipi_reduction = mv.ipi_reduction
                        line.ipi_base = mv.ipi_base
                        line.ii_tax_id = mv.ii_tax_id.id
                        line.ii_base = mv.ii_base
                        line.ii_value = mv.ii_value
                        line.ii_iof_value = mv.ii_iof_value
                        line.ii_customhouse_charges = mv.ii_customhouse_charges
                        line.pis_tax_id = mv.pis_tax_id.id
                        line.pis_base_type = mv.pis_base_type
                        line.pis_percent = mv.pis_percent
                        line.pis_reduction = mv.pis_reduction
                        line.pis_base = mv.pis_base
                        line.pis_value = mv.pis_value
                        line.cofins_tax_id = mv.cofins_tax_id.id
                        line.cofins_base_type = mv.cofins_base_type
                        line.cofins_percent = mv.cofins_percent
                        line.cofins_reduction = mv.cofins_reduction
                        line.cofins_base = mv.cofins_base
                        line.cofins_value = mv.cofins_value
                        if moves.fiscal_operation_id.fiscal_operation_type == "in":
                            line.cofins_cst_id = mv.cofins_tax_id.cst_out_id.id
                            line.pis_cst_id = mv.pis_tax_id.cst_out_id.id
                            line.ipi_cst_id = mv.ipi_tax_id.cst_out_id.id
                        else:
                            line.cofins_cst_id = mv.cofins_tax_id.cst_in_id.id
                            line.pis_cst_id = mv.pis_tax_id.cst_in_id.id
                            line.ipi_cst_id = mv.ipi_tax_id.cst_in_id.id
                        
                numero_itens -= 1
        # Carlos fim


        # Create action.
        action = {
            'name': _('Reverse Moves'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
        }
        if len(moves_to_redirect) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': moves_to_redirect.id,
                'context': {'default_move_type':  moves_to_redirect.move_type},
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', moves_to_redirect.ids)],
            })
            if len(set(moves_to_redirect.mapped('move_type'))) == 1:
                action['context'] = {'default_move_type':  moves_to_redirect.mapped('move_type').pop()}
        return action
