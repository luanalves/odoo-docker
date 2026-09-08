# -*- coding: utf-8 -*-
"""
T040 [US8] — Unit tests for CMS observability events.

Tests (using unittest.mock — no Odoo environment required):
- change_status() emits cms.page.status_changed with all required fields
- transition → published emits additionally cms.page.published with published_at
- upload() emits cms_media_uploads_total with labels company_id, mime_type, type
- CSS injection detected emits cms.css_injection_blocked with company_id + field
  BEFORE the ValueError is raised (ordering guarantee)
"""
import importlib
import pathlib
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

# ---------------------------------------------------------------------------
# The service modules under test (services/cms_page_service.py etc.) are
# plain Python — they don't import `odoo` at module scope, only a deferred
# `from odoo.addons.thedevkitchen_observability.services.tracer import
# add_span_event` inside their own _emit() function, at call time. Since
# these tests always run inside the real Odoo container (via
# tests/run_unit_tests.py), that target module genuinely exists — so each
# TestCase below patches its `add_span_event` attribute directly with
# unittest.mock.patch() rather than trying to inject a fake replacement
# module into sys.modules. Patching the real module's attribute is immune to
# import ordering: it works identically whether some other test file
# (imported earlier during unittest's discovery) already triggered a
# genuine import of this module or not — unlike a sys.modules injection,
# which can only ever apply if the real module hasn't been imported by
# anyone yet, and previously caused this file to leak an incomplete fake
# (missing trace_http_request) into every test file discovered afterward.
_TRACER_ADD_SPAN_EVENT = "odoo.addons.thedevkitchen_observability.services.tracer.add_span_event"


def _load(rel_path):
    """Load a module from an absolute path without Odoo's module finder."""
    base = pathlib.Path(__file__).parents[2]  # thedevkitchen_cms root
    full = base / rel_path
    spec = importlib.util.spec_from_file_location(rel_path.replace("/", "."), full)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helper to build a minimal mock page
# ---------------------------------------------------------------------------

def _make_page(page_id=1, slug="test-page", status="draft", published_at=None, company_id=10):
    page = MagicMock()
    page.id = page_id
    page.slug = slug
    page.status = status
    page.published_at = published_at
    page.company_id.id = company_id
    page.content_ids = []
    return page


# ---------------------------------------------------------------------------
# Test: CmsPageService.change_status — span events
# ---------------------------------------------------------------------------

class TestChangeStatusEvents(unittest.TestCase):
    def setUp(self):
        """Reload the service module fresh so _emit is clean."""
        patcher = patch(_TRACER_ADD_SPAN_EVENT, new=MagicMock())
        self.mock_add_span_event = patcher.start()
        self.addCleanup(patcher.stop)
        self.svc_mod = _load("services/cms_page_service.py")

    def _make_env(self, page):
        env = MagicMock()
        env.uid = 42
        env["thedevkitchen.cms.page"].sudo().search.return_value = page
        env["thedevkitchen.cms.page"].sudo().browse.return_value = page
        # read_group returns counts per status for gauge
        env["thedevkitchen.cms.page"].sudo().read_group.return_value = [
            {"status": "draft", "status_count": 2},
            {"status": "pending_review", "status_count": 1},
            {"status": "published", "status_count": 0},
            {"status": "archived", "status_count": 0},
        ]
        return env

    def test_status_changed_event_emitted(self):
        """change_status() emits cms.page.status_changed with required fields."""
        page = _make_page(status="draft")
        env = self._make_env(page)

        self.svc_mod.CmsPageService.change_status(env, 1, "pending_review", 10)

        calls = [c for c in self.mock_add_span_event.call_args_list
                 if c[0][0] == "cms.page.status_changed"]
        self.assertEqual(len(calls), 1, "cms.page.status_changed should be emitted once")

        attrs = calls[0][0][1]
        self.assertIn("company_id", attrs)
        self.assertIn("page_id", attrs)
        self.assertIn("slug", attrs)
        self.assertIn("from_status", attrs)
        self.assertIn("to_status", attrs)
        self.assertIn("author_id", attrs)
        self.assertEqual(attrs["from_status"], "draft")
        self.assertEqual(attrs["to_status"], "pending_review")

    def test_published_event_emitted_on_publish(self):
        """Transition → published emits cms.page.published with published_at."""
        page = _make_page(status="pending_review", published_at=None)
        env = self._make_env(page)

        self.svc_mod.CmsPageService.change_status(env, 1, "published", 10)

        events = [c[0][0] for c in self.mock_add_span_event.call_args_list]
        self.assertIn("cms.page.status_changed", events)
        self.assertIn("cms.page.published", events)

        pub_call = next(c for c in self.mock_add_span_event.call_args_list
                        if c[0][0] == "cms.page.published")
        attrs = pub_call[0][1]
        self.assertIn("published_at", attrs)
        self.assertTrue(attrs["published_at"])  # non-empty

    def test_published_event_not_emitted_for_other_transitions(self):
        """cms.page.published must NOT be emitted for non-published transitions."""
        page = _make_page(status="draft")
        env = self._make_env(page)

        self.svc_mod.CmsPageService.change_status(env, 1, "pending_review", 10)

        events = [c[0][0] for c in self.mock_add_span_event.call_args_list]
        self.assertNotIn("cms.page.published", events)

    def test_pages_by_status_gauge_emitted(self):
        """change_status() emits cms.pages_by_status gauge event."""
        page = _make_page(status="draft")
        env = self._make_env(page)

        self.svc_mod.CmsPageService.change_status(env, 1, "pending_review", 10)

        events = [c[0][0] for c in self.mock_add_span_event.call_args_list]
        self.assertIn("cms.pages_by_status", events)

    def test_invalid_transition_does_not_emit(self):
        """Invalid transition raises ValueError and does not emit events."""
        page = _make_page(status="published")
        env = self._make_env(page)

        with self.assertRaises(ValueError) as ctx:
            self.svc_mod.CmsPageService.change_status(env, 1, "draft", 10)

        self.assertIn("invalid_status_transition", str(ctx.exception))
        events = [c[0][0] for c in self.mock_add_span_event.call_args_list]
        self.assertNotIn("cms.page.status_changed", events)


# ---------------------------------------------------------------------------
# Test: CmsMediaService.upload — counter event
# ---------------------------------------------------------------------------

class TestMediaUploadCounter(unittest.TestCase):
    def setUp(self):
        patcher = patch(_TRACER_ADD_SPAN_EVENT, new=MagicMock())
        self.mock_add_span_event = patcher.start()
        self.addCleanup(patcher.stop)
        self.media_mod = _load("services/cms_media_service.py")

    def _make_env(self, media_id=99):
        env = MagicMock()
        attachment = MagicMock()
        attachment.id = 55
        env["ir.attachment"].sudo().create.return_value = attachment
        env["ir.config_parameter"].sudo().get_param.return_value = "http://localhost:8069"
        media = MagicMock()
        media.id = media_id
        env["thedevkitchen.cms.media"].sudo().create.return_value = media
        return env

    def test_counter_emitted_after_successful_upload(self):
        """upload() emits cms_media_uploads_total with company_id, mime_type, type."""
        # Build a minimal valid JPEG bytes header so magic can detect it
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        env = self._make_env()

        with patch.object(
            self.media_mod.CmsMediaService, "validate_upload",
            return_value={
                "media_type": "image",
                "detected_mime": "image/jpeg",
                "filename": "test.jpg",
                "size": 104,
            }
        ):
            self.media_mod.CmsMediaService.upload(env, fake_jpeg, "test.jpg", "image/jpeg", 10)

        calls = [c for c in self.mock_add_span_event.call_args_list
                 if c[0][0] == "cms_media_uploads_total"]
        self.assertEqual(len(calls), 1, "cms_media_uploads_total should be emitted once")

        attrs = calls[0][0][1]
        self.assertEqual(attrs.get("company_id"), "10")
        self.assertEqual(attrs.get("mime_type"), "image/jpeg")
        self.assertEqual(attrs.get("type"), "image")

    def test_counter_not_emitted_on_validation_failure(self):
        """No counter event emitted when validation raises ValueError."""
        env = self._make_env()

        with patch.object(
            self.media_mod.CmsMediaService, "validate_upload",
            side_effect=ValueError("unsupported_mime|application/octet-stream"),
        ):
            with self.assertRaises(ValueError):
                self.media_mod.CmsMediaService.upload(
                    env, b"garbage", "file.bin", "application/octet-stream", 10
                )

        calls = [c for c in self.mock_add_span_event.call_args_list
                 if c[0][0] == "cms_media_uploads_total"]
        self.assertEqual(len(calls), 0)


# ---------------------------------------------------------------------------
# Test: CmsSettingsService.update_settings — CSS injection event ordering
# ---------------------------------------------------------------------------

class TestCssInjectionEventOrdering(unittest.TestCase):
    """Verify that cms.css_injection_blocked is emitted BEFORE ValueError is raised."""

    def setUp(self):
        patcher = patch(_TRACER_ADD_SPAN_EVENT, new=MagicMock())
        self.mock_add_span_event = patcher.start()
        self.addCleanup(patcher.stop)
        self.settings_mod = _load("services/cms_settings_service.py")

    def _make_env(self, company_id=10):
        env = MagicMock()
        settings = MagicMock()
        settings.id = 1
        settings.company_id.id = company_id
        settings.company_slug = "test-slug"
        settings.og_default_title = None
        settings.og_default_description = None
        settings.custom_css = None
        settings.custom_js = None
        settings.custom_js_last_modified_by = None
        settings.custom_js_last_modified_at = None
        settings.create_date = None
        settings.write_date = None
        # Stub get_or_create
        env["thedevkitchen.cms.settings"].get_or_create = MagicMock(return_value=settings)
        # Also stub the observability event model (used in update_settings)
        obs_event = MagicMock()
        env["thedevkitchen.observability.event"].sudo().emit = obs_event
        return env, settings, obs_event

    def test_css_injection_blocked_event_before_error(self):
        """cms.css_injection_blocked event MUST be emitted before ValueError is raised."""
        env, settings, obs_emit = self._make_env(company_id=10)

        emitted_before_raise = []

        def track_emit(name, attrs=None):
            emitted_before_raise.append(name)

        self.mock_add_span_event.side_effect = track_emit

        with self.assertRaises(ValueError) as ctx:
            self.settings_mod.CmsSettingsService.update_settings(
                env,
                {"custom_css": "body { width: expression(alert(1)) }"},
                company_id=10,
                user_role="owner",
            )

        self.assertIn("css_injection_detected", str(ctx.exception))
        # The event should have been emitted before the error
        # (obs_emit is the Odoo model emit — it may or may not be called
        #  depending on whether the model is available; the tracer mock is definitive)
        # Since we stub the model emit and it doesn't raise, the tracer path
        # may not fire (the service uses the model path). Check model emit instead.
        obs_emit.assert_called_once()
        call_args = obs_emit.call_args
        self.assertEqual(call_args[0][0], "cms.css_injection_blocked")
        payload = call_args[0][1]
        self.assertEqual(payload["company_id"], 10)
        self.assertEqual(payload["field"], "custom_css")

    def test_no_event_for_safe_css(self):
        """Safe CSS should not emit css_injection_blocked."""
        env, settings, obs_emit = self._make_env(company_id=10)

        self.settings_mod.CmsSettingsService.update_settings(
            env,
            {"custom_css": "body { color: red; }"},
            company_id=10,
            user_role="owner",
        )

        obs_emit.assert_not_called()

    def test_all_five_injection_patterns_blocked(self):
        """Each of the 5 CSS injection patterns triggers the event."""
        patterns = [
            "body { width: expression(alert(1)) }",
            "body { behavior: url(foo.htc) }",
            "body { background: url(javascript:alert(1)) }",
            "@import url('evil.css');",
            "body { -moz-binding: url('xss.xml') }",
        ]
        for css in patterns:
            env, settings, obs_emit = self._make_env(company_id=10)
            with self.assertRaises(ValueError, msg=f"Pattern not blocked: {css}"):
                self.settings_mod.CmsSettingsService.update_settings(
                    env, {"custom_css": css}, company_id=10, user_role="owner"
                )
            obs_emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
