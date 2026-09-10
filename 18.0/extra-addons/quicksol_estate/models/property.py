# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Property(models.Model):
    _name = "real.estate.property"
    _description = "Property"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "create_date desc"

    # ========== BASIC INFO ==========
    name = fields.Char(string="Property Name", required=True, tracking=True)
    reference_code = fields.Char(
        string="Reference Code", copy=False, tracking=True, index=True
    )
    active = fields.Boolean(default=True)

    # ========== OWNER DATA ==========
    owner_id = fields.Many2one(
        "real.estate.property.owner", string="Owner", tracking=True
    )
    owner_name = fields.Char(
        string="Owner Name", related="owner_id.name", readonly=True
    )
    owner_partner_id = fields.Many2one(
        "res.partner",
        string="Owner Partner",
        related="owner_id.partner_id",
        readonly=True,
        store=True,
        help="Related partner for Portal access",
    )
    phone_ids = fields.One2many(
        "real.estate.property.phone", "property_id", string="Contact Phones"
    )
    email_ids = fields.One2many(
        "real.estate.property.email", "property_id", string="Contact Emails"
    )
    owner_email = fields.Char(string="Owner Email")
    owner_home_phone = fields.Char(string="Owner Home Phone")
    owner_business_phone = fields.Char(string="Owner Business Phone")
    owner_mobile_phone = fields.Char(string="Owner Mobile Phone")
    origin_media = fields.Selection(
        [
            ("website", "Website"),
            ("social_media", "Social Media"),
            ("referral", "Referral"),
            ("walk_in", "Walk-in"),
            ("phone", "Phone"),
            ("email", "Email"),
            ("partner", "Partner"),
            ("other", "Other"),
        ],
        string="Origin Media",
        required=True,
        default="website",
        tracking=True,
    )
    activity_notification = fields.Selection(
        [
            ("all", "All Activities"),
            ("important", "Important Only"),
            ("none", "None"),
        ],
        string="Activity Notification",
        default="important",
    )
    send_activities_to_owner = fields.Boolean(string="Send Activities to Owner")

    # ========== STRUCTURE ==========
    property_purpose = fields.Selection(
        [
            ("residential", "Residential"),
            ("commercial", "Commercial"),
            ("industrial", "Industrial"),
            ("rural", "Rural"),
            ("vacation", "Vacation/Temporary"),
            ("corporate", "Corporate"),
        ],
        string="Purpose",
        required=True,
        default="residential",
        tracking=True,
    )

    property_type_id = fields.Many2one(
        "real.estate.property.type",
        string="Property Type",
        required=True,
        tracking=True,
    )
    building_id = fields.Many2one(
        "real.estate.property.building", string="Building/Condominium", tracking=True
    )
    building_name = fields.Char(
        string="Building Name", related="building_id.name", readonly=True
    )
    floor_number = fields.Integer(string="Floor Number")
    unit_number = fields.Char(string="Unit Number")

    # ========== LOCATION ==========
    # CEP and Address
    zip_code = fields.Char(string="CEP", size=9, required=True, tracking=True)
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        default=lambda self: self.env.ref("base.br").id,
        required=True,
        tracking=True,
    )
    state_id = fields.Many2one(
        "res.country.state",
        string="State",
        required=True,
        tracking=True,
        domain="[('country_id.code', '=', 'BR')]",
    )
    city = fields.Char(string="City", required=True, tracking=True)
    neighborhood = fields.Char(string="Neighborhood", tracking=True)
    street = fields.Char(string="Street", required=True, tracking=True)
    street_number = fields.Char(string="Number", required=True)
    complement = fields.Char(string="Complement")
    address = fields.Text(
        string="Complete Address", compute="_compute_address", store=True
    )

    # Geolocation
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))

    # ========== PRIMARY DATA ==========
    # Intentions
    for_sale = fields.Boolean(string="For Sale", default=True, tracking=True)
    for_rent = fields.Boolean(string="For Rent", tracking=True)
    registered_by = fields.Char(string="Registered By")
    alternative_reference = fields.Char(string="Alternative Reference")
    intention = fields.Char(string="Intention")

    # Pricing
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    price = fields.Monetary(
        string="Sale Price", currency_field="currency_id", tracking=True
    )
    rent_price = fields.Monetary(
        string="Rent Price", currency_field="currency_id", tracking=True
    )

    # Taxes and Insurance
    iptu_annual = fields.Monetary(string="IPTU Annual", currency_field="currency_id")
    iptu_monthly = fields.Monetary(
        string="IPTU Monthly", compute="_compute_iptu_monthly", store=True
    )
    iptu_payment_condition = fields.Char(string="IPTU Payment Condition")
    iptu_value = fields.Char(string="IPTU Value")
    rental_guarantee_insurance = fields.Char(string="Rental Guarantee Insurance")
    fire_insurance = fields.Char(string="Fire Insurance")
    insurance_value = fields.Monetary(
        string="Insurance Value", currency_field="currency_id"
    )
    condominium_fee = fields.Monetary(
        string="Condominium Fee", currency_field="currency_id"
    )

    # Status
    property_status = fields.Selection(
        [
            ("available", "Available"),
            ("occupied", "Occupied"),
            ("rented", "Rented"),
            ("reserved", "Reserved"),
            ("sold", "Sold"),
            ("under_construction", "Under Construction"),
            ("maintenance", "Under Maintenance"),
        ],
        string="Property Status",
        required=True,
        default="available",
        tracking=True,
    )
    exclusivity = fields.Boolean(string="Exclusivity")
    property_situation = fields.Selection(
        [
            ("Não Informado", "Não Informado"),
            ("Desocupado", "Desocupado"),
            ("Ocupado", "Ocupado"),
            ("Reservado", "Reservado"),
            ("Em construção", "Em construção"),
            ("Lançamento", "Lançamento"),
            ("Novo", "Novo"),
        ],
        string="Property Situation",
        default="Não Informado",
    )

    location_type_id = fields.Many2one(
        "real.estate.location.type",
        string="Location Type",
        required=True,
        tracking=True,
    )

    # Authorization
    authorization_start_date = fields.Date(
        string="Authorization Start Date", tracking=True
    )
    authorization_end_date = fields.Date(string="Authorization End Date", tracking=True)
    authorization_active = fields.Boolean(
        string="Authorization Active",
        compute="_compute_authorization_active",
        store=True,
    )

    # Financial Options
    accepts_fgts = fields.Boolean(string="Accepts FGTS")
    used_fgts = fields.Boolean(
        string="FGTS Used Previously",
        help="Indicates whether this property is known to have used FGTS in a previous acquisition or construction transaction.",
    )
    fgts_last_usage_date = fields.Date(
        string="Last FGTS Usage Date",
        help="Registry/reference date of the last known FGTS use for this property.",
    )
    fgts_eligible_from = fields.Date(
        string="FGTS Eligible From",
        compute="_compute_fgts_eligibility",
        store=True,
        help="First date when the property can use FGTS again after the 3-year restriction window.",
    )
    fgts_eligible_now = fields.Boolean(
        string="FGTS Eligible Now",
        compute="_compute_fgts_eligibility",
        store=True,
        help="Indicates whether the property is currently outside the FGTS 3-year restriction window.",
    )
    fgts_usage_notes = fields.Text(string="FGTS Usage Notes")
    accepts_financing = fields.Boolean(string="Accepts Financing", default=True)

    # ========== FEATURES/CHARACTERISTICS ==========
    # Areas
    area = fields.Float(string="Built Area (m²)", required=True, tracking=True)
    total_area = fields.Float(string="Total Area (m²)", tracking=True)
    private_area = fields.Float(string="Private Area (m²)")
    land_area = fields.Float(string="Land Area (m²)")

    # Rooms and Spaces
    num_rooms = fields.Integer(string="Bedrooms")
    num_suites = fields.Integer(string="Suites")
    num_bathrooms = fields.Integer(string="Bathrooms")
    num_parking = fields.Integer(string="Parking Spaces")
    num_floors = fields.Integer(string="Number of Floors")

    # Construction
    construction_year = fields.Integer(string="Construction Year")
    reform_year = fields.Integer(string="Reform Year")
    property_age = fields.Integer(
        string="Property Age (years)", compute="_compute_property_age", store=True
    )

    # Condition
    condition = fields.Selection(
        [
            ("new", "New"),
            ("excellent", "Excellent"),
            ("good", "Good"),
            ("fair", "Fair"),
            ("needs_renovation", "Needs Renovation"),
            ("under_construction", "Under Construction"),
        ],
        string="Condition",
        required=True,
        default="good",
        tracking=True,
    )

    # Amenities
    amenities = fields.Many2many("real.estate.amenity", string="Amenities")

    # ========== ZONING ==========
    zoning_type = fields.Selection(
        [
            ("residential", "Residential"),
            ("commercial", "Commercial"),
            ("mixed", "Mixed Use"),
            ("industrial", "Industrial"),
            ("agricultural", "Agricultural"),
        ],
        string="Zoning Type",
    )
    zoning_restrictions = fields.Text(string="Zoning Restrictions")

    # ========== MARKERS/TAGS ==========
    tag_ids = fields.Many2many("real.estate.property.tag", string="Tags")

    # ========== KEY CONTROL ==========
    key_ids = fields.One2many("real.estate.property.key", "property_id", string="Keys")
    has_keys = fields.Boolean(string="Has Keys", compute="_compute_has_keys")
    key_location = fields.Char(string="Key Location")

    # ========== PHOTOS ==========
    image = fields.Binary(string="Main Property Image", attachment=True)
    photo_ids = fields.One2many(
        "real.estate.property.photo", "property_id", string="Photo Gallery"
    )
    photo_count = fields.Integer(string="Photo Count", compute="_compute_photo_count")

    # ========== WEB PUBLISHING ==========
    publish_website = fields.Boolean(string="Publish on Website", default=False)
    publish_featured = fields.Boolean(string="Featured Property")
    publish_super_featured = fields.Boolean(string="Super Featured")
    youtube_video_url = fields.Char(string="YouTube Video URL")
    virtual_tour_url = fields.Char(string="Virtual Tour URL")

    # SEO
    meta_title = fields.Char(string="Meta Title", size=60)
    meta_description = fields.Text(string="Meta Description", size=160)
    meta_keywords = fields.Char(string="Meta Keywords")

    # Descriptions
    description = fields.Html(string="Property Description")
    description_short = fields.Text(string="Short Description", size=250)
    internal_notes = fields.Text(string="Internal Notes (Confidential)")

    # ========== SIGNS AND BANNERS ==========
    has_sign = fields.Boolean(string="Has Sign/Banner")
    sign_installation_date = fields.Date(string="Sign Installation Date")
    sign_removal_date = fields.Date(string="Sign Removal Date")
    sign_type = fields.Selection(
        [
            ("sale", "For Sale"),
            ("rent", "For Rent"),
            ("sold", "Sold"),
            ("rented", "Rented"),
        ],
        string="Sign Type",
    )
    sign_notes = fields.Text(string="Sign Notes")

    # ========== COMMISSIONS ==========
    commission_ids = fields.One2many(
        "real.estate.property.commission", "property_id", string="Commissions"
    )
    total_commission = fields.Monetary(
        string="Total Commission",
        compute="_compute_total_commission",
        currency_field="currency_id",
    )
    commission_type = fields.Char(string="Commission Type")
    captured_intention = fields.Char(string="Captured Intention")
    included_in_commission_date = fields.Date(string="Included in Commission Date")
    commercial_condition = fields.Char(string="Commercial Condition")

    # ========== DOCUMENTS ==========
    document_ids = fields.One2many(
        "real.estate.property.document", "property_id", string="Documents"
    )
    document_count = fields.Integer(
        string="Document Count", compute="_compute_document_count"
    )
    matricula_number = fields.Char(string="Matrícula Number")
    iptu_code = fields.Char(string="IPTU Code")
    electricity_network_code = fields.Char(string="Electricity Network Code")
    water_network_code = fields.Char(string="Water Network Code")
    titles_rights = fields.Char(string="Titles Rights")
    approved_environmental_agency = fields.Boolean(
        string="Approved Environmental Agency"
    )
    approved_project = fields.Boolean(string="Approved Project")
    documentation_observations = fields.Text(string="Documentation Observations")
    cnpj_owner = fields.Char(string="Owner CNPJ", size=18)

    # ========== RELATIONSHIPS ==========
    company_id = fields.Many2one(
        "res.company",
        string="Real Estate Company",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env.company,
        help="Company this property belongs to",
    )
    agent_id = fields.Many2one(
        "real.estate.agent", string="Responsible Agent", tracking=True
    )
    prospector_id = fields.Many2one(
        "real.estate.agent",
        string="Prospector",
        tracking=True,
        help="Agent who originally prospected/registered this property. Earns commission split when another agent completes the sale.",
    )
    profile_id = fields.Many2one(
        "thedevkitchen.estate.profile", string="Current Profile", ondelete="set null"
    )
    sale_id = fields.Many2one("real.estate.sale", string="Sale")
    lease_id = fields.Many2one("real.estate.lease", string="Lease")

    # ========== ASSIGNMENT RELATIONSHIPS (US3) ==========
    assignment_ids = fields.One2many(
        "real.estate.agent.property.assignment",
        "property_id",
        string="Agent Assignments",
    )

    assigned_agent_ids = fields.Many2many(
        "real.estate.agent",
        compute="_compute_assigned_agents",
        string="Assigned Agents",
        help="All agents assigned to this property",
    )

    # ========== LEGACY FIELDS (for compatibility) ==========
    status = fields.Selection(
        [
            ("available", "Available"),
            ("pending", "Pending"),
            ("sold", "Sold"),
            ("rented", "Rented"),
        ],
        string="Status (Legacy)",
        default="available",
    )

    # ========== FEATURE 013: PROPOSAL RELATIONSHIPS ==========
    proposal_ids = fields.One2many(
        "real.estate.proposal",
        "property_id",
        string="Proposals",
        help="All proposals submitted for this property",
    )

    active_proposal_id = fields.Many2one(
        "real.estate.proposal",
        string="Active Proposal",
        compute="_compute_active_proposal",
        store=True,
        help="The current active (draft/sent/accepted) root proposal for this property",
    )

    @api.depends(
        "proposal_ids.state", "proposal_ids.active", "proposal_ids.parent_proposal_id"
    )
    def _compute_active_proposal(self):
        Proposal = self.env["real.estate.proposal"]

        for prop in self:
            prop.active_proposal_id = False

        if not self.ids:
            return

        proposals = Proposal.search(
            [
                ("property_id", "in", self.ids),
                ("state", "in", ("draft", "sent", "accepted")),
                ("active", "=", True),
                ("parent_proposal_id", "=", False),
            ],
            order="property_id asc, create_date asc, id asc",
        )

        first_active_by_property = {}
        for proposal in proposals:
            property_id = proposal.property_id.id
            if property_id not in first_active_by_property:
                first_active_by_property[property_id] = proposal

        for prop in self:
            prop.active_proposal_id = first_active_by_property.get(prop.id, False)

    def write(self, vals):
        """When a property is archived, cancel all non-terminal proposals (FR-047)."""
        result = super().write(vals)
        if vals.get("active") is False:
            TERMINAL = ("accepted", "rejected", "expired", "cancelled")
            for prop in self:
                live_proposals = prop.proposal_ids.filtered(
                    lambda p: p.state not in TERMINAL
                )
                if live_proposals:
                    live_proposals.action_cancel(
                        "Proposta cancelada automaticamente: imóvel arquivado."
                    )
        return result

    def init(self):
        """Create database indexes for common search queries"""
        super(Property, self).init()

        # Composite index for the public property listing hot path
        # (Feature 029): every public request filters by
        # company_id + publish_website + active and sorts by create_date.
        self._cr.execute(
            """
            CREATE INDEX IF NOT EXISTS real_estate_property_public_listing_idx
            ON real_estate_property (company_id, publish_website, active, create_date)
        """
        )

    # ========== COMPUTED FIELDS ==========
    @api.depends(
        "street",
        "street_number",
        "complement",
        "neighborhood",
        "city",
        "state_id",
        "zip_code",
        "country_id",
    )
    def _compute_address(self):
        for prop in self:
            address_parts = []
            if prop.street:
                street_full = prop.street
                if prop.street_number:
                    street_full += f", {prop.street_number}"
                if prop.complement:
                    street_full += f" - {prop.complement}"
                address_parts.append(street_full)
            if prop.neighborhood:
                address_parts.append(prop.neighborhood)
            if prop.city:
                city_state = prop.city
                if prop.state_id:
                    city_state += f" - {prop.state_id.code}"
                address_parts.append(city_state)
            if prop.zip_code:
                address_parts.append(f"CEP: {prop.zip_code}")
            if prop.country_id:
                address_parts.append(prop.country_id.name)
            prop.address = "\n".join(address_parts) if address_parts else ""

    @api.depends("iptu_annual")
    def _compute_iptu_monthly(self):
        for prop in self:
            prop.iptu_monthly = prop.iptu_annual / 12 if prop.iptu_annual else 0

    @api.depends("authorization_start_date", "authorization_end_date")
    def _compute_authorization_active(self):
        today = fields.Date.today()
        for prop in self:
            if prop.authorization_start_date and prop.authorization_end_date:
                prop.authorization_active = (
                    prop.authorization_start_date
                    <= today
                    <= prop.authorization_end_date
                )
            elif prop.authorization_start_date:
                prop.authorization_active = prop.authorization_start_date <= today
            else:
                prop.authorization_active = False

    @api.depends("used_fgts", "fgts_last_usage_date")
    def _compute_fgts_eligibility(self):
        today = fields.Date.today()
        for prop in self:
            if not prop.used_fgts:
                prop.fgts_eligible_from = False
                prop.fgts_eligible_now = True
                continue

            if not prop.fgts_last_usage_date:
                prop.fgts_eligible_from = False
                prop.fgts_eligible_now = False
                continue

            eligible_from = prop.fgts_last_usage_date + relativedelta(years=3, days=1)
            prop.fgts_eligible_from = eligible_from
            prop.fgts_eligible_now = today >= eligible_from

    @api.depends("construction_year")
    def _compute_property_age(self):
        current_year = fields.Date.today().year
        for prop in self:
            if prop.construction_year:
                prop.property_age = current_year - prop.construction_year
            else:
                prop.property_age = 0

    @api.depends("key_ids")
    def _compute_has_keys(self):
        for prop in self:
            prop.has_keys = bool(prop.key_ids)

    @api.depends("photo_ids")
    def _compute_photo_count(self):
        for prop in self:
            prop.photo_count = len(prop.photo_ids)

    @api.depends("commission_ids", "commission_ids.commission_amount")
    def _compute_total_commission(self):
        for prop in self:
            prop.total_commission = sum(prop.commission_ids.mapped("commission_amount"))

    @api.depends("document_ids")
    def _compute_document_count(self):
        for prop in self:
            prop.document_count = len(prop.document_ids)

    @api.depends("assignment_ids", "assignment_ids.agent_id")
    def _compute_assigned_agents(self):
        """Compute list of agents assigned to this property"""
        for prop in self:
            active_assignments = prop.assignment_ids.filtered(lambda a: a.active)
            prop.assigned_agent_ids = active_assignments.mapped("agent_id")

    # ========== CONSTRAINTS ==========
    @api.constrains("for_sale", "for_rent")
    def _check_intentions(self):
        for prop in self:
            if not prop.for_sale and not prop.for_rent:
                raise ValidationError("Property must be for sale, for rent, or both.")

    @api.constrains("price", "rent_price")
    def _check_prices(self):
        for prop in self:
            if prop.for_sale and (not prop.price or prop.price <= 0):
                raise ValidationError(
                    "Sale price must be greater than zero when property is for sale."
                )
            if prop.for_rent and (not prop.rent_price or prop.rent_price <= 0):
                raise ValidationError(
                    "Rent price must be greater than zero when property is for rent."
                )

    @api.constrains("area", "total_area")
    def _check_areas(self):
        for prop in self:
            if prop.area and prop.area <= 0:
                raise ValidationError("Built area must be greater than zero.")
            if prop.total_area and prop.total_area < prop.area:
                raise ValidationError("Total area cannot be less than built area.")

    @api.constrains("construction_year", "reform_year")
    def _check_years(self):
        current_year = fields.Date.today().year
        for prop in self:
            if prop.construction_year and (
                prop.construction_year < 1800
                or prop.construction_year > current_year + 5
            ):
                raise ValidationError(
                    f"Construction year must be between 1800 and {current_year + 5}."
                )
            if (
                prop.reform_year
                and prop.construction_year
                and prop.reform_year < prop.construction_year
            ):
                raise ValidationError("Reform year cannot be before construction year.")

    @api.constrains("authorization_start_date", "authorization_end_date")
    def _check_authorization_dates(self):
        for prop in self:
            if prop.authorization_start_date and prop.authorization_end_date:
                if prop.authorization_end_date < prop.authorization_start_date:
                    raise ValidationError(
                        "Authorization end date cannot be before start date."
                    )

    # ========== ONCHANGE METHODS ==========
    @api.onchange("zip_code")
    def _onchange_zip_code(self):
        """CEP search integration point - to be implemented with Brazilian CEP API"""
        if self.zip_code and len(self.zip_code.replace("-", "").replace(".", "")) == 8:
            # TODO: Integrate with ViaCEP API or similar
            # For now, just format the CEP
            cep_clean = self.zip_code.replace("-", "").replace(".", "")
            self.zip_code = f"{cep_clean[:5]}-{cep_clean[5:]}"

    @api.onchange("building_id")
    def _onchange_building(self):
        """Auto-fill location from building"""
        if self.building_id:
            self.zip_code = self.building_id.zip_code
            self.city = self.building_id.city
            self.state = self.building_id.state
            self.country_id = self.building_id.country_id
            self.condominium_fee = self.building_id.monthly_fee

    # ========== ACTIONS ==========
    def action_view_photos(self):
        return {
            "name": "Photos",
            "type": "ir.actions.act_window",
            "res_model": "real.estate.property.photo",
            "view_mode": "kanban,list,form",
            "domain": [("property_id", "=", self.id)],
            "context": {"default_property_id": self.id},
        }

    def action_view_documents(self):
        return {
            "name": "Documents",
            "type": "ir.actions.act_window",
            "res_model": "real.estate.property.document",
            "view_mode": "list,form",
            "domain": [("property_id", "=", self.id)],
            "context": {"default_property_id": self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        # Emit property.before_create event for each property (sync validation)
        event_bus = self.env["quicksol.event.bus"]

        # Get current user's agent/prospector record for auto-assignment
        current_agent = self.env["real.estate.agent"].search(
            [("user_id", "=", self.env.uid)], limit=1
        )

        for vals in vals_list:
            event_bus.emit("property.before_create", vals, force_sync=True)

            # Auto-generate reference code if not provided
            if not vals.get("reference_code"):
                vals["reference_code"] = (
                    self.env["ir.sequence"].next_by_code("real.estate.property")
                    or "NEW"
                )

            # Auto-assign agent/prospector if user is an agent and no prospector_id provided
            if current_agent and not vals.get("prospector_id"):
                # Check if user is a prospector (has Prospector group)
                if self.env.user.has_group(
                    "quicksol_estate.group_real_estate_prospector"
                ):
                    vals["prospector_id"] = current_agent.id
                # Check if user is an agent (has Agent group)
                elif self.env.user.has_group("quicksol_estate.group_real_estate_agent"):
                    if not vals.get("agent_id"):
                        vals["agent_id"] = current_agent.id

        properties = super().create(vals_list)

        # Emit property.created event for each created property (async notifications)
        for prop in properties:
            event_bus.emit(
                "property.created", {"property_id": prop.id, "property": prop}
            )

        return properties

    @api.model
    def _seed_fix_owner_relationships(self):
        owner = self.env.ref(
            "quicksol_estate.seed_property_owner", raise_if_not_found=False
        )
        if not owner:
            return True

        properties = self.browse(
            [
                prop.id
                for prop in (
                    self.env.ref(
                        "quicksol_estate.seed_property_1", raise_if_not_found=False
                    ),
                    self.env.ref(
                        "quicksol_estate.seed_property_2", raise_if_not_found=False
                    ),
                    self.env.ref(
                        "quicksol_estate.seed_property_3", raise_if_not_found=False
                    ),
                )
                if prop
            ]
        ).exists()
        if properties:
            properties.write({"owner_id": owner.id})
        return True


class PropertyType(models.Model):
    _name = "real.estate.property.type"
    _description = "Property Type"

    name = fields.Char(string="Type Name", required=True)
    active = fields.Boolean(default=True)


class PropertyTag(models.Model):
    _name = "real.estate.property.tag"
    _description = "Property Tag"
    _rec_name = "name"

    name = fields.Char(string="Tag Name", required=True)
    color = fields.Integer(string="Color")
    active = fields.Boolean(default=True)


# Keep compatibility with old PropertyImage model
class PropertyImage(models.Model):
    _name = "real.estate.property.image"
    _description = "Property Image (Legacy)"

    image = fields.Binary("Image", required=True)
    description = fields.Char("Image Description")
    property_id = fields.Many2one(
        "real.estate.property", string="Property", ondelete="cascade"
    )
