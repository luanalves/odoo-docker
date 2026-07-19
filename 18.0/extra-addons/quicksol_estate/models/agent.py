# -*- coding: utf-8 -*-

import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from ..services.creci_validator import CreciValidator


class RealEstateAgent(models.Model):
    _name = "real.estate.agent"
    _description = "Real Estate Agent/Broker"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name asc"

    # ==================== CORE FIELDS ====================

    name = fields.Char(
        "Full Name", required=True, tracking=True, help="Agent full legal name"
    )

    cpf = fields.Char(
        "CPF",
        size=14,  # Format: 123.456.789-01
        required=True,
        tracking=True,
        index=True,
        help="Brazilian individual taxpayer registry (CPF)",
    )

    creci = fields.Char(
        "CRECI",
        size=50,
        tracking=True,
        help="Real estate broker license (optional for trainees/assistants). "
        "Accepts flexible formats: CRECI/SP 12345, CRECI-RJ-67890, 12345-MG",
    )

    creci_normalized = fields.Char(
        "CRECI Normalized",
        size=20,
        compute="_compute_creci_normalized",
        store=True,
        index=True,
        help="Normalized CRECI in format: CRECI/UF NNNNN",
    )

    creci_state = fields.Char(
        "CRECI State",
        size=2,
        compute="_compute_creci_parts",
        store=True,
        help="State (UF) from CRECI",
    )

    creci_number = fields.Char(
        "CRECI Number",
        size=8,
        compute="_compute_creci_parts",
        store=True,
        help="Number from CRECI",
    )

    # Contact
    email = fields.Char("Email", tracking=True, help="Agent email address")

    phone = fields.Char(
        "Phone", size=20, tracking=True, help="Brazilian format: +55 (11) 99999-9999"
    )

    mobile = fields.Char("Mobile", size=20, tracking=True, help="Mobile phone number")

    # Multi-tenancy - Many2one for single company
    company_id = fields.Many2one(
        "res.company",
        "Real Estate Company",
        required=True,
        default=lambda self: self._get_default_company(),
        ondelete="restrict",
        tracking=True,
        help="Real estate company this agent belongs to",
    )

    # User account link (optional)
    user_id = fields.Many2one(
        "res.users",
        "Related User",
        ondelete="restrict",
        index=True,
        help="Link to user account if agent has system access",
    )

    # Profile link (Feature 010: Profile Unification)
    profile_id = fields.Many2one(
        "thedevkitchen.estate.profile",
        "Unified Profile",
        ondelete="restrict",
        index=True,
        help="Link to unified profile record (9 RBAC types). "
        "Agents are a business extension of the agent profile type.",
    )

    # ==================== STATUS & LIFECYCLE ====================

    active = fields.Boolean(
        "Active",
        default=True,
        tracking=True,
        help="Uncheck to deactivate agent. Inactive agents are hidden but preserve historical data.",
    )

    hire_date = fields.Date(
        "Hire Date",
        default=fields.Date.today,
        required=True,
        tracking=True,
        help="Date when agent was hired",
    )

    deactivation_date = fields.Date(
        "Deactivation Date",
        readonly=True,
        tracking=True,
        help="Date when agent was deactivated",
    )

    deactivation_reason = fields.Text(
        "Deactivation Reason",
        readonly=True,
        tracking=True,
        help="Reason for deactivation",
    )

    # ==================== FINANCIAL ====================

    bank_name = fields.Char("Bank Name")
    bank_branch = fields.Char("Branch", size=10)
    bank_account = fields.Char("Account Number", size=20)
    bank_account_type = fields.Selection(
        [("checking", "Checking Account"), ("savings", "Savings Account")],
        string="Account Type",
    )
    pix_key = fields.Char("PIX Key", help="Brazilian instant payment key")

    # ==================== LEGACY FIELDS (keep for compatibility) ====================

    properties = fields.One2many(
        "real.estate.property", "agent_id", string="Properties"
    )
    agency_name = fields.Char("Agency Name")
    years_experience = fields.Integer("Years of Experience")
    profile_picture = fields.Binary("Profile Picture")

    # ==================== ASSIGNMENT FIELDS (US3) ====================

    agent_property_ids = fields.Many2many(
        "real.estate.property",
        compute="_compute_agent_properties",
        string="Assigned Properties",
        help="Properties assigned to this agent",
    )

    assigned_property_count = fields.Integer(
        compute="_compute_assigned_property_count", string="Assigned Properties Count"
    )

    assignment_ids = fields.One2many(
        "real.estate.agent.property.assignment",
        "agent_id",
        string="Property Assignments",
    )

    # ==================== COMMISSION FIELDS (US4) ====================

    commission_rule_ids = fields.One2many(
        "real.estate.commission.rule",
        "agent_id",
        string="Commission Rules",
        help="Commission rules configured for this agent",
    )

    commission_transaction_ids = fields.One2many(
        "real.estate.commission.transaction",
        "agent_id",
        string="Commission Transactions",
        help="Historical commission transactions for this agent",
    )

    # ==================== PERFORMANCE METRICS (US5) ====================

    total_sales_count = fields.Integer(
        compute="_compute_total_sales_count",
        string="Total Sales",
        help="Total number of commission transactions (sales)",
    )

    total_commissions = fields.Float(
        compute="_compute_total_commissions",
        string="Total Commissions",
        digits="Product Price",
        help="Sum of all commission amounts (in BRL)",
    )

    average_commission = fields.Float(
        compute="_compute_average_commission",
        string="Average Commission",
        digits="Product Price",
        help="Average commission amount per transaction (in BRL)",
    )

    active_properties_count = fields.Integer(
        compute="_compute_active_properties_count",
        string="Active Properties",
        help="Count of currently active property assignments",
    )

    # ==================== CONSTRAINTS ====================

    _sql_constraints = [
        (
            "cpf_company_unique",
            "UNIQUE(cpf, company_id)",
            "CPF já cadastrado para esta imobiliária",
        )
    ]

    # ==================== COMPUTED FIELDS ====================

    @api.depends("creci")
    def _compute_creci_normalized(self):
        """Normalize CRECI to standard format"""
        for agent in self:
            if agent.creci:
                try:
                    agent.creci_normalized = CreciValidator.normalize(agent.creci)
                except ValidationError:
                    agent.creci_normalized = False
            else:
                agent.creci_normalized = False

    @api.depends("creci_normalized")
    def _compute_creci_parts(self):
        """Extract state and number from normalized CRECI"""
        for agent in self:
            if agent.creci_normalized:
                agent.creci_state = CreciValidator.extract_state(agent.creci_normalized)
                agent.creci_number = CreciValidator.extract_number(
                    agent.creci_normalized
                )
            else:
                agent.creci_state = False
                agent.creci_number = False

    @api.depends("assignment_ids", "assignment_ids.property_id")
    def _compute_agent_properties(self):
        """Compute list of properties assigned to this agent"""
        for agent in self:
            active_assignments = agent.assignment_ids.filtered(lambda a: a.active)
            agent.agent_property_ids = active_assignments.mapped("property_id")

    @api.depends("agent_property_ids")
    def _compute_assigned_property_count(self):
        """Count assigned properties"""
        for agent in self:
            agent.assigned_property_count = len(agent.agent_property_ids)

    # ==================== VALIDATION ====================

    @api.constrains("cpf")
    def _check_cpf_format(self):
        """Validate CPF format and checksum"""
        try:
            from validate_docbr import CPF

            cpf_validator = CPF()
        except ImportError:
            # validate_docbr not installed - skip validation
            return

        for agent in self:
            if agent.cpf:
                # Remove formatting
                cpf_clean = "".join(filter(str.isdigit, agent.cpf))

                if not cpf_validator.validate(cpf_clean):
                    raise ValidationError(_("CPF inválido: %s") % agent.cpf)

    @api.constrains("creci", "creci_normalized", "company_id")
    def _check_creci_format(self):
        """Validate CRECI format and uniqueness"""
        for agent in self:
            if agent.creci:
                # Normalize will raise ValidationError if invalid
                normalized = CreciValidator.normalize(agent.creci)
                CreciValidator.validate(normalized)

                # Check uniqueness within company
                if agent.company_id and agent.creci_normalized:
                    duplicate = self.search(
                        [
                            ("id", "!=", agent.id),
                            ("creci_normalized", "=", agent.creci_normalized),
                            ("company_id", "=", agent.company_id.id),
                        ],
                        limit=1,
                    )
                    if duplicate:
                        raise ValidationError(
                            _("CRECI %s já cadastrado para esta imobiliária")
                            % agent.creci_normalized
                        )

    @api.constrains("user_id", "company_id")
    def _check_user_unique(self):
        """Ensure user is not linked to multiple agents in the same company"""
        for agent in self:
            if agent.user_id:
                duplicate = self.search(
                    [
                        ("id", "!=", agent.id),
                        ("user_id", "=", agent.user_id.id),
                        ("company_id", "=", agent.company_id.id),
                    ],
                    limit=1,
                )
                if duplicate:
                    raise ValidationError(
                        _(
                            "Este usuário já está vinculado a outro agente nesta imobiliária"
                        )
                    )

    @api.constrains("email")
    def _check_email_format(self):
        """Validate email format with strict regex"""
        email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        for agent in self:
            if agent.email and not email_pattern.match(agent.email):
                raise ValidationError(_("Email inválido: %s") % agent.email)

    @api.constrains("phone", "mobile")
    def _check_phone_format(self):
        """Validate Brazilian phone format"""
        try:
            import phonenumbers
        except ImportError:
            # phonenumbers not installed - skip validation
            return

        for agent in self:
            for phone_field in [agent.phone, agent.mobile]:
                if phone_field:
                    try:
                        # Parse as Brazilian number
                        parsed = phonenumbers.parse(phone_field, "BR")
                        if not phonenumbers.is_valid_number(parsed):
                            raise ValidationError(
                                _(
                                    "Telefone inválido: %s. Use formato: +55 (11) 99999-9999"
                                )
                                % phone_field
                            )
                    except phonenumbers.NumberParseException:
                        raise ValidationError(
                            _("Telefone inválido: %s. Use formato: +55 (11) 99999-9999")
                            % phone_field
                        )

    # ==================== ACTIONS ====================

    def action_deactivate(self, reason=None):
        """
        Deactivate agent (soft-delete following ADR-015).

        Args:
            reason (str): Optional reason for deactivation
        """
        self.ensure_one()

        if not self.active:
            raise UserError(_("Agent já está desativado"))

        self.write(
            {
                "active": False,
                "deactivation_date": fields.Date.today(),
                "deactivation_reason": reason or "Deactivated via API",
            }
        )

        return True

    def action_reactivate(self):
        """Reactivate agent"""
        self.ensure_one()

        if self.active:
            raise UserError(_("Agent já está ativo"))

        self.write(
            {"active": True, "deactivation_date": False, "deactivation_reason": False}
        )

        return True

    # ==================== DEFAULTS ====================

    def _get_default_company(self):
        """Get default company from user"""
        # Use native res.users company_id
        if self.env.user.company_id:
            return self.env.user.company_id
        # Fallback to first real estate company
        companies = self.env["res.company"].search(
            [("is_real_estate", "=", True)], limit=1
        )
        return companies[0] if companies else False

    # ==================== LEGACY METHODS (keep for compatibility) ====================

    @api.onchange("user_id")
    def _onchange_user_id(self):
        """Sync agent data with user data when user is selected"""
        if self.user_id:
            # Only fill empty fields (preserve existing data)
            if not self.name:
                self.name = self.user_id.name
            if not self.email:
                self.email = self.user_id.email

            # Sync companies from user's native company_ids
            user_companies = self.user_id.company_ids
            if user_companies:
                # Set company_id (Many2one) to first company if not set
                if not self.company_id or self.company_id not in user_companies:
                    self.company_id = user_companies[0]

    @api.model
    def create(self, vals):
        """Override create to sync user data and handle company_ids from user"""
        # Feature 010: If profile_id is provided, sync cadastral data from profile (T14)
        # Uses setdefault() to allow explicit values to take precedence
        if vals.get("profile_id"):
            profile = (
                self.env["thedevkitchen.estate.profile"]
                .sudo()
                .browse(vals["profile_id"])
            )
            if profile.exists():
                # Sync cadastral fields using setdefault (don't override explicit values)
                vals.setdefault("name", profile.name)
                vals.setdefault("cpf", profile.document)  # document → cpf
                vals.setdefault("email", profile.email)
                vals.setdefault("phone", profile.phone)
                vals.setdefault("mobile", profile.mobile)
                vals.setdefault("company_id", profile.company_id.id)
                if profile.hire_date:
                    vals.setdefault("hire_date", profile.hire_date)

        # If user_id is provided, sync data from user
        if vals.get("user_id"):
            user = self.env["res.users"].browse(vals["user_id"])

            # Sync company from user's native company_ids
            if user.company_ids:
                # Set company_id if not explicitly provided (use first company)
                if "company_id" not in vals:
                    vals["company_id"] = user.company_ids[0].id

        agent = super().create(vals)

        return agent

    def write(self, vals):
        """Override write to maintain synchronization"""
        # Sync company from user when user_id changes
        if "user_id" in vals and "company_id" not in vals:
            user = self.env["res.users"].browse(vals["user_id"])
            if user and user.company_ids:
                vals["company_id"] = user.company_ids[0].id

        result = super().write(vals)

        return result

    # ==================== PERFORMANCE COMPUTED METHODS (US5) ====================

    @api.depends(
        "commission_transaction_ids", "commission_transaction_ids.transaction_type"
    )
    def _compute_total_sales_count(self):
        """
        Compute total number of commission transactions (sales)

        Business Logic:
        - Count all commission transactions regardless of payment status
        - Only count 'sale' type transactions (exclude 'rental')
        - Multi-tenant isolated (only transactions for this agent's company)
        """
        for agent in self:
            agent.total_sales_count = len(
                agent.commission_transaction_ids.filtered(
                    lambda t: t.transaction_type == "sale"
                )
            )

    @api.depends(
        "commission_transaction_ids", "commission_transaction_ids.commission_amount"
    )
    def _compute_total_commissions(self):
        """
        Compute total sum of all commission amounts

        Business Logic:
        - Sum commission_amount from all transactions
        - Includes pending, paid, and cancelled transactions
        - Returns Monetary value in agent's currency (BRL default)
        """
        for agent in self:
            agent.total_commissions = sum(
                agent.commission_transaction_ids.mapped("commission_amount")
            )

    @api.depends(
        "commission_transaction_ids",
        "commission_transaction_ids.commission_amount",
        "total_sales_count",
    )
    def _compute_average_commission(self):
        """
        Compute average commission amount per transaction

        Business Logic:
        - Average = total_commissions / total_sales_count
        - Returns 0 if no transactions exist
        """
        for agent in self:
            if agent.total_sales_count > 0:
                agent.average_commission = (
                    agent.total_commissions / agent.total_sales_count
                )
            else:
                agent.average_commission = 0.0

    @api.depends("assignment_ids", "assignment_ids.active")
    def _compute_active_properties_count(self):
        """
        Compute count of currently active property assignments

        Business Logic:
        - Count assignment_ids where active=True
        - Only assignments for this agent's company (automatic via record rules)
        """
        for agent in self:
            agent.active_properties_count = len(agent.assignment_ids.filtered("active"))

    # ==================== SMART BUTTON ACTIONS (Phase 8) ====================

    def action_view_properties(self):
        """
        Smart button action: Open list of properties assigned to this agent

        Returns:
            dict: Action to open property assignments tree view
        """
        self.ensure_one()
        return {
            "name": f"Properties - {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "real.estate.agent.property.assignment",
            "view_mode": "list,form",
            "domain": [("agent_id", "=", self.id)],
            "context": {"default_agent_id": self.id},
        }

    def action_view_commission_transactions(self):
        """
        Smart button action: Open list of commission transactions for this agent

        Returns:
            dict: Action to open commission transactions tree view
        """
        self.ensure_one()
        return {
            "name": f"Commission Transactions - {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "real.estate.commission.transaction",
            "view_mode": "list,form",
            "domain": [("agent_id", "=", self.id)],
            "context": {"default_agent_id": self.id},
        }
