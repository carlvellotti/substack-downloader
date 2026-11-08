"""Archive paging tests: `python -m unittest test_scraper` from this checkout. No network."""

import unittest
from unittest import mock

import requests

import scraper
from scraper import SubstackScraper


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Client Error")

    def json(self):
        return self.payload


def posts(prefix, n):
    return [{"slug": f"{prefix}-{i}"} for i in range(n)]


class ArchivePagingTest(unittest.TestCase):
    def run_scrape(self, pages, limit=None):
        client = SubstackScraper("https://example.substack.com")
        calls, saved = [], []

        def get(url, params=None):
            calls.append(dict(params))
            return pages[len(calls) - 1]

        client.session.get = get
        client.get_post = lambda slug: {"slug": slug}
        client.save_post = lambda post, output_dir, **kw: saved.append(post["slug"])
        with mock.patch.object(scraper.time, "sleep"), mock.patch.object(scraper.os, "makedirs"):
            client.scrape(output_dir="unused", limit=limit)
        return calls, saved

    def test_cursor_api_follows_next_cursor_and_never_sends_offset(self):
        calls, saved = self.run_scrape([
            FakeResponse({"posts": posts("a", 12), "nextCursor": "c1"}),
            FakeResponse({"posts": posts("b", 12), "nextCursor": "c2"}),
            FakeResponse({"posts": posts("c", 5), "nextCursor": None}),
        ])
        self.assertEqual([c.get("cursor") for c in calls], [None, "c1", "c2"])
        self.assertTrue(all("offset" not in c for c in calls))
        self.assertEqual(len(saved), 29)

    def test_full_last_cursor_page_stops_without_another_request(self):
        calls, saved = self.run_scrape([FakeResponse({"posts": posts("a", 12), "nextCursor": None})])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(saved), 12)

    def test_limit_across_a_cursor_page_boundary(self):
        calls, saved = self.run_scrape([
            FakeResponse({"posts": posts("a", 12), "nextCursor": "c1"}),
            FakeResponse({"posts": posts("b", 2), "nextCursor": "c2"}),
        ], limit=14)
        self.assertEqual([(c["limit"], c.get("cursor")) for c in calls], [(12, None), (2, "c1")])
        self.assertEqual(len(saved), 14)

    def test_list_api_still_pages_by_offset(self):
        calls, saved = self.run_scrape([FakeResponse(posts("a", 12)), FakeResponse(posts("b", 3))])
        self.assertEqual([c.get("offset") for c in calls], [None, 12])
        self.assertEqual(len(saved), 15)

    def test_rejected_archive_request_exits_nonzero(self):
        rejected = FakeResponse({"errors": [{"param": "offset", "msg": "Invalid value"}]}, status=400)
        with mock.patch.object(scraper.SubstackScraper, "scrape",
                               side_effect=requests.exceptions.HTTPError("400 Client Error")), \
                mock.patch("sys.argv", ["scraper.py", "--url", "https://example.substack.com",
                                        "--cookie", "x"]):
            with self.assertRaises(SystemExit) as raised:
                scraper.main()
        self.assertEqual(raised.exception.code, 1)
        with self.assertRaises(requests.exceptions.HTTPError):
            client = SubstackScraper("https://example.substack.com")
            client.session.get = lambda url, params=None: rejected
            client.get_archive()


if __name__ == "__main__":
    unittest.main()
