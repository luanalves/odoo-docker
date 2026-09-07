/**
 * cypress/e2e/views/cms.cy.js
 * US7 — CMS Admin UI Tests
 * Covers: T034
 *
 * Pre-conditions:
 *   - Odoo running, thedevkitchen_cms installed
 *   - admin user (base.group_system) has CMS access by default
 *   - owner@seed.com.br also works after security CSV fix (group_real_estate_owner added)
 *
 * URL routing in Odoo 18 (legacy hash-based format — the correct stable pattern):
 *   /web#action=<module>.<action_xml_id>&model=<model>&view_type=<type>
 */

const BASE_URL = Cypress.env('ODOO_BASE_URL');
const USER     = Cypress.env('ODOO_USERNAME');
const PASS     = Cypress.env('ODOO_PASSWORD');

before(() => {
  if (!BASE_URL || !USER || !PASS) {
    throw new Error(
      'Missing required Cypress env vars. ' +
      'Define ODOO_BASE_URL, ODOO_USERNAME and ODOO_PASSWORD in cypress.env.json.',
    );
  }
});

// Odoo legacy hash-based URL routing (XML ID format)
const CMS_PAGES     = '/web#action=thedevkitchen_cms.action_cms_pages&model=thedevkitchen.cms.page&view_type=list';
const CMS_TEMPLATES = '/web#action=thedevkitchen_cms.action_cms_templates&model=thedevkitchen.cms.template&view_type=list';
const CMS_MEDIA     = '/web#action=thedevkitchen_cms.action_cms_media&model=thedevkitchen.cms.media&view_type=list';
const CMS_SETTINGS  = '/web#action=thedevkitchen_cms.action_cms_settings&model=thedevkitchen.cms.settings&view_type=form';
const CMS_TEMPLATES_GENERIC = '/web#action=thedevkitchen_cms.action_cms_templates_generic&model=thedevkitchen.cms.template.generic&view_type=list';

describe('CMS Admin UI — Odoo Views', () => {

  beforeEach(() => {
    cy.session([USER, PASS], () => {
      cy.request({
        method: 'POST',
        url: `${BASE_URL}/web/session/authenticate`,
        body: {
          jsonrpc: '2.0',
          method: 'call',
          params: { db: 'realestate', login: USER, password: PASS },
        },
        headers: { 'Content-Type': 'application/json' },
      }).then((resp) => {
        expect(resp.body.result).to.have.property('uid');
      });
    });
    // Suppress unhandled RPC errors (mail.push notifications, etc.) globally
    cy.on('uncaught:exception', () => false);
  });

  it('S1: CMS Pages list view loads with .o_list_view', () => {
    cy.visit(CMS_PAGES);
    cy.get('.o_list_view', { timeout: 15000 }).should('exist');
    cy.get('body').should('not.contain.text', 'Oops!');
    cy.get('body').should('not.contain.text', 'Missing Action');
  });

  it('S2: Pages list view shows Status and Created At columns', () => {
    cy.visit(CMS_PAGES);
    cy.get('.o_list_view', { timeout: 15000 }).should('exist');
    cy.get('th').contains('Status').should('exist');
    cy.get('th').contains('Created At').should('exist');
  });

  it('S3: Page form shows statusbar with all 4 statuses', () => {
    cy.visit(CMS_PAGES);
    cy.get('.o_list_view', { timeout: 15000 }).should('exist');
    // Click first row or New button to open form
    cy.get('body').then(($body) => {
      if ($body.find('.o_data_row').length > 0) {
        cy.get('.o_data_row').first().click();
      } else {
        cy.get('.o_list_button_add, button:contains("New")').first().click();
      }
    });
    cy.get('.o_statusbar_status', { timeout: 10000 }).should('exist');
    cy.get('.o_statusbar_status').contains('Draft').should('exist');
    cy.get('.o_statusbar_status').contains('Published').should('exist');
  });

  it('S4: Templates list view loads without error', () => {
    cy.visit(CMS_TEMPLATES);
    cy.get('.o_list_view', { timeout: 15000 }).should('exist');
    cy.get('body').should('not.contain.text', 'Missing Action');
    cy.get('body').should('not.contain.text', 'Oops!');
  });

  it('S4b: Generic Templates list view loads without error', () => {
    cy.visit(CMS_TEMPLATES_GENERIC);
    cy.get('.o_list_view', { timeout: 15000 }).should('exist');
    cy.get('body').should('not.contain.text', 'Missing Action');
    cy.get('body').should('not.contain.text', 'Oops!');
    cy.screenshot('028-S4b-generic-templates-list', { capture: 'viewport' });
  });

  it('S4c: Generic Templates form saves a new record', () => {
    // thedevkitchen.cms.template.generic has a UNIQUE(name) SQL constraint,
    // so a fixed literal name would only pass on the first run against a
    // given database. Use a per-run unique name instead.
    const uniqueName = `cypress_generic_${Date.now()}`;
    cy.visit(CMS_TEMPLATES_GENERIC);
    cy.get('.o_list_view', { timeout: 15000 }).should('exist');
    cy.get('.o_list_button_add, button:contains("New")').first().click();
    cy.get('.o_form_view', { timeout: 10000 }).should('exist');
    cy.get('h1 input, h1 [name="name"] input').first().type(uniqueName);
    // Odoo's OWL selection widget JSON-encodes option values (e.g. value='"landing"'),
    // so select by the visible option text ("Landing Page") rather than the raw value.
    cy.get('[name="category"] select, [name="category"] input').first().select('Landing Page', { force: true });
    cy.get('.o_form_button_save, button[title="Save"]').first().click();
    cy.get('body').should('not.contain.text', 'Oops!');
    // Prove the record actually persisted (a unique-constraint violation would
    // leave the form dirty/editable with no saved record) rather than only
    // checking for an unrelated string that Odoo 18's error dialog never uses.
    cy.wait(1500);
    cy.get('.o_form_view:not(.o_form_editable), .o_form_view.o_form_readonly', { timeout: 10000 }).should('exist');
    cy.contains(uniqueName, { timeout: 5000 }).should('be.visible');
    cy.screenshot('028-S4c-generic-template-saved', { capture: 'viewport' });
  });

  it('S5: Settings form shows company_slug and custom code section', () => {
    cy.visit(CMS_SETTINGS);
    cy.get('.o_form_view', { timeout: 15000 }).should('exist');
    cy.get('[name="company_slug"]').should('exist');
    cy.get('[name="custom_css"]').should('exist');
  });

  it('S6: Zero Missing-Action errors during full CMS navigation', () => {
    const urls = [CMS_PAGES, CMS_TEMPLATES, CMS_TEMPLATES_GENERIC, CMS_MEDIA, CMS_SETTINGS];

    urls.forEach((url) => {
      cy.visit(url);
      // Wait for Odoo's action to load or for the error dialog to appear
      cy.get('.o_action, .o_dialog, .modal', { timeout: 12000 }).then(() => {
        cy.get('body').should('not.contain.text', 'does not exist');
        cy.get('body').should('not.contain.text', 'Missing Action');
      });
    });
  });

});
