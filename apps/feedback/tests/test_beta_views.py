from datetime import datetime

from django.conf import settings

from nose.tools import eq_
from pyquery import PyQuery as pq

from input import (FIREFOX, LATEST_BETAS, OPINION_PRAISE, OPINION_ISSUE,
                   MAX_FEEDBACK_LENGTH)
from input.tests import ViewTestCase, enforce_ua
from input.urlresolvers import reverse
from feedback.models import Opinion


class BetaViewTests(ViewTestCase):
    """Tests for our beta feedback submissions."""

    fixtures = ['feedback/opinions']
    FX_UA = ('Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10.6; '
             'de; rv:1.9.2.3) Gecko/20100401 Firefox/%s')

    def _get_page(self, ver=None):
        """Request beta feedback page."""
        extra = dict(HTTP_USER_AGENT=self.FX_UA % ver) if ver else {}
        return self.client.get(reverse('feedback.sad'), **extra)

    @enforce_ua
    def test_no_ua(self):
        """No UA: Redirect to beta download."""
        r = self._get_page()
        eq_(r.status_code, 302)
        assert r['Location'].endswith(
                reverse('feedback.download', channel='beta'))

    @enforce_ua
    def test_release(self):
        """Release version on beta page: redirect."""
        r = self._get_page('3.6')
        eq_(r.status_code, 302)
        assert r['Location'].endswith(reverse('feedback', channel='release'))

    @enforce_ua
    def test_old_beta(self):
        """Old beta: redirect."""
        r = self._get_page('3.6b2')
        eq_(r.status_code, 302)
        assert r['Location'].endswith(
                reverse('feedback.download', channel='beta'))

    @enforce_ua
    def test_latest_beta(self):
        """Latest beta: no redirect."""
        r = self._get_page(LATEST_BETAS[FIREFOX])
        eq_(r.status_code, 200)

    @enforce_ua
    def test_newer_beta(self):
        """Beta version newer than current: no redirect."""
        r = self._get_page('20.0b2')
        eq_(r.status_code, 200)

    @enforce_ua
    def test_nightly(self):
        """Nightly version: redirect."""
        r = self._get_page('20.0b2pre')
        eq_(r.status_code, 302)
        assert r['Location'].endswith(
                reverse('feedback.download', channel='beta'))

    def test_give_feedback(self):
        r = self.client.post(reverse('feedback.sad'))
        eq_(r.content, 'User-Agent request header must be set.')

    def test_opinion_detail(self):
        r = self.client.get(reverse('opinion.detail', args=(29,)))
        eq_(r.status_code, 200)

    def test_url_submission(self):
        def submit_url(url, valid=True):
            """Submit feedback with a given URL, check if it's accepted."""
            data = {
                # Need to vary text so we don't cause duplicates warnings.
                'description': 'Hello %d' % datetime.now().microsecond,
                'add_url': 'on',
                'type': OPINION_PRAISE.id,
            }

            if url:
                data['url'] = url

            r = self.client.post(reverse('feedback.happy'), data,
                                 HTTP_USER_AGENT=(self.FX_UA % '20.0b2'),
                                 follow=True)
            # Neither valid nor invalid URLs cause anything but a 200 response.
            eq_(r.status_code, 200)
            if valid:
                assert r.content.find('Thanks') >= 0
                assert r.content.find('Enter a valid URL') == -1
            else:
                assert r.content.find('Thanks') == -1
                assert r.content.find('Enter a valid URL') >= 0

        # Valid URL types
        submit_url('http://example.com')
        submit_url('https://example.com')
        submit_url('about:me')
        submit_url('chrome://mozapps/content/extensions/extensions.xul')

        # Invalid URL types
        submit_url('gopher://something', valid=False)
        submit_url('zomg', valid=False)

        # Try submitting add_url=on with no URL. Bug 613549.
        submit_url(None)

    def test_submissions_without_url(self):
        """Ensure feedback without URL can be submitted. Bug 610023."""
        req = lambda: self.client.post(
            reverse('feedback.sad'), {
                'description': 'Hello!',
                'type': OPINION_ISSUE.id,
            }, HTTP_USER_AGENT=(self.FX_UA % '20.0b2'), follow=True)
        # No matter what you submit in the URL field, there must be a 200
        # response code.
        r = req()
        eq_(r.status_code, 200)
        assert r.content.find('Thanks for') >= 0

        # Resubmit, should not work due to duplicate submission.
        r2 = req()
        eq_(r2.status_code, 200)
        assert r2.content.find('We already got your feedback') >= 0

    def test_submission_autocomplete_off(self):
        """
        Ensure both mobile and desktop submission pages have autocomplete off.
        """
        def autocomplete_check(site_id):
            r = self.client.get(reverse('feedback.sad'), HTTP_USER_AGENT=(
                self.FX_UA % '20.0b2'), SITE_ID=site_id, follow=True)
            doc = pq(r.content)
            form = doc('#feedbackform form')

            assert form
            eq_(form.attr('autocomplete'), 'off')

        autocomplete_check(settings.DESKTOP_SITE_ID)
        autocomplete_check(settings.MOBILE_SITE_ID)

    def test_submission_with_device_info(self):
        """Ensure mobile device info can be submitted."""
        r = self.client.post(
            reverse('feedback.sad'), {
                'description': 'Hello!',
                'type': OPINION_ISSUE.id,
                'manufacturer': 'FancyBrand',
                'device': 'FancyPhone 2.0',
            }, HTTP_USER_AGENT=(self.FX_UA % '20.0b2'), follow=True)
        eq_(r.status_code, 200)
        assert r.content.find('Thanks') >= 0

        # Fetch row from model and check data made it there.
        latest = Opinion.objects.no_cache().order_by('-id')[0]
        eq_(latest.manufacturer, 'FancyBrand')
        eq_(latest.device, 'FancyPhone 2.0')

    def test_feedback_index(self):
        """Test feedback index page for Betas."""
        r = self.client.get(reverse('feedback', channel='beta'),
                            HTTP_USER_AGENT=(self.FX_UA % '20.0b2'),
                            follow=True)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        for link in ('feedback.happy', 'feedback.sad'):
            eq_(doc('a[href$="%s"]' % reverse(link)).length, 1)

    def test_max_length(self):
        """
        Ensure description's max_length attribute is propagated correctly for
        JS to pick up.
        """
        for link in ('feedback.happy', 'feedback.sad'):
            r = self.client.get(reverse(link, channel='beta'),
                                HTTP_USER_AGENT=(self.FX_UA % '20.0b2'),
                                follow=True)
            doc = pq(r.content)
            eq_(doc('#count').attr('data-max'),
                str(MAX_FEEDBACK_LENGTH))


