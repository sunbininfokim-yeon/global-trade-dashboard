from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import ust_toolkit_feed as tf  # noqa: E402

RSS = """<rss><channel>
<item><pubDate>Mon, 02 Nov 2026 14:04:51 -0600</pubDate><title>Treasury Announces Marketable Borrowing Estimates</title>
  <link>https://content.govdelivery.com/accounts/USTREAS/bulletins/43161a8</link><description><![CDATA[<p>text</p>]]></description></item>
<item><pubDate>Tue, 10 Nov 2026 18:45:07 -0600</pubDate><title>Remarks from Secretary of the Treasury at the Economic Club</title>
  <link>https://content.govdelivery.com/accounts/USTREAS/bulletins/1</link>
  <description><![CDATA[<p>We will keep coupon issuance steady and lean on Treasury bills; buybacks support the long end.</p>]]></description></item>
<item><pubDate>Wed, 11 Nov 2026 09:00:00 -0600</pubDate><title>Treasury Sanctions Drug Trafficking Organizations</title>
  <link>https://content.govdelivery.com/accounts/USTREAS/bulletins/2</link><description>sanctions</description></item>
</channel></rss>"""
LIST = ('<div><time datetime="2026-11-04T12:00:00Z">November 4, 2026</time><a href="/news/press-releases/sb0678">'
        'Quarterly Refunding Statement of Assistant Secretary for Financial Markets</a></div>'
        '<div><time datetime="2026-11-02T12:00:00Z">November 2, 2026</time><a href="/news/press-releases/sb0675">'
        'Treasury Announces Marketable Borrowing Estimates</a></div>')


class Feed(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(tf.classify("Treasury Announces Increased Sizes of Buybacks", None)[0], "buyback")
        self.assertEqual(tf.classify("Quarterly Refunding Statement", None)[0], "refunding")
        self.assertIsNone(tf.classify("Treasury Sanctions X", "sanctions only")[0])
        self.assertIsNone(tf.classify("Remarks at a dinner", "trade and China")[0])
        self.assertEqual(tf.classify("Remarks at a dinner", "coupon issuance and treasury bills")[0], "speech")

    def test_update_merges_sources_and_keeps_treasury_url(self):
        fresh = tf.parse_govdelivery(RSS) + tf.parse_press_list(LIST)
        items = tf.update([], fresh, lambda u: "", "2026-11-25")
        by = {i["title"][:20]: i for i in items}
        self.assertEqual(by["Treasury Announces M"]["url"], "https://home.treasury.gov/news/press-releases/sb0675")
        self.assertEqual(by["Quarterly Refunding "]["kind"], "refunding")
        self.assertEqual(by["Remarks from Secreta"]["kind"], "speech")
        self.assertNotIn("Treasury Sanctions D", by)
        self.assertEqual([i["date"] for i in items], ["2026-11-10", "2026-11-04", "2026-11-02"])
        # A second run with the same releases adds nothing.
        self.assertEqual(tf.update(items, fresh, lambda u: "", "2026-11-26"), items)


if __name__ == "__main__":
    unittest.main()
