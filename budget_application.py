from odoo import models, fields, api

class BudgetApplication(models.Model):
    _name = "budget.application"
    _inherit = ['mail.thread']

    message_follower_ids = fields.Many2many('res.partner', 'budget_application_res_partner_rel',
                                            'budget_application_id', 'partner_id', string='Followers')

    name = fields.Char(string="Budget Application Name", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('budget.application'))
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    total_budget = fields.Monetary(string="Total Budget", currency_field='currency_id')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string="Status", default='draft')
    approval_stage = fields.Selection([
        ('draft', 'Draft'),
        ('level_1', 'Level 1 Approval'),
        ('level_2', 'Level 2 Approval'),
        ('level_3', 'Level 3 Approval'),
        ('approved', 'Fully Approved'),
        ('rejected', 'Rejected'),
    ], string="Approval Stage", default='draft', track_visibility='onchange')

    approval_ids = fields.One2many('budgetlines.approval', 'budget_id', string="Approval Lines")
    current_approver_id = fields.Many2one('res.users', string="Current Approver", compute='_compute_current_approver',
                                          store=True)

    currency_id = fields.Many2one('res.currency', string="Currency", required=True,
                                  default=lambda self: self.env.company.currency_id)
    line_ids = fields.One2many('budgetline.application', 'budget_id', string="Budget Lines")
    description = fields.Text(string="Description")

    @api.depends('approval_ids.status')
    def _compute_current_approver(self):
        for record in self:
            pending_approval = record.approval_ids.filtered(lambda a: a.status == 'pending')
            record.current_approver_id = pending_approval[0].approver_id if pending_approval else False

    def action_submit_for_approval(self):
        self.ensure_one()
        if self.approval_stage == 'draft':
            self.approval_stage = 'level_1'
            self._create_approval_line(level='1')

    def action_approve(self):
        self.ensure_one()
        pending_approval = self.approval_ids.filtered(lambda a: a.status == 'pending')
        if pending_approval:
            pending_approval[0].write({'status': 'approved', 'approval_date': fields.Date.today()})
            next_stage = {
                'level_1': 'level_2',
                'level_2': 'level_3',
                'level_3': 'approved',
            }
            self.approval_stage = next_stage.get(self.approval_stage, 'approved')
            if self.approval_stage in ['level_2', 'level_3']:
                self._create_approval_line(level=self.approval_stage.split('_')[1])
        else:
            self.approval_stage = 'approved'

    def action_reject(self):
        self.ensure_one()
        pending_approval = self.approval_ids.filtered(lambda a: a.status == 'pending')
        if pending_approval:
            pending_approval[0].write({'status': 'rejected', 'approval_date': fields.Date.today()})
        self.approval_stage = 'rejected'

    def _create_approval_line(self, level):
        self.ensure_one()
        if not self.approval_ids.filtered(lambda a: a.level == level):
            self.env['budgetlines.approval'].create({
                'budget_id': self.id,
                'level': level,
                'status': 'pending',
            })


class BudgetLinesApproval(models.Model):
    _name = 'budgetlines.approval'

    budget_id = fields.Many2one('budget.application', string="Budget", required=True, ondelete='cascade')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string="Status", default='pending')
    approval_date = fields.Date(string="Approval Date")
    approver_id = fields.Many2one('res.users', string="Approver")
    comments = fields.Text(string="Comments")


class BudgetApplicationLine(models.Model):
    _name = 'budgetline.application'

    name = fields.Char(string="Budget Line Name", required=True)
    expense_category_id = fields.Many2one('account.account', string="Expense Category")
    allocated_amount = fields.Monetary(string="Allocated Amount", required=True, currency_field='currency_id')
    actual_spend = fields.Monetary('Actual Spend', currency_field='currency_id')
    donor_fund_id = fields.Many2one('donor.fund', string="Donor Fund")
    budget_id = fields.Many2one('budget.application', string="Budget", required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='budget_id.currency_id', store=True)
    variance = fields.Monetary(string="Variance", compute='_compute_variance', store=True)

    @api.depends('allocated_amount', 'actual_spend')
    def _compute_variance(self):
        for record in self:
            record.variance = record.allocated_amount - record.actual_spend
