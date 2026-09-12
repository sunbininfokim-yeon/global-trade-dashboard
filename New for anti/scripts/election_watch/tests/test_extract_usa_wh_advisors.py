import unittest

from election_watch.extract_usa_wh_advisors import classify_topical_advisors


def row(name_en, title, salary=1.0, status="EMPLOYEE"):
    return {
        "payroll_name": name_en,
        "name_en": name_en,
        "status": status,
        "salary_usd": salary,
        "title": title,
        "title_u": title.upper(),
    }


class ClassifyTopicalAdvisorsTests(unittest.TestCase):
    def test_named_portfolio_kept_generic_policy_dropped(self):
        classified = classify_topical_advisors(
            [
                row("Marco A. Rubio", "ASSISTANT TO THE PRESIDENT AND NATIONAL SECURITY ADVISOR"),
                row("Paula M. White", "SENIOR ADVISOR TO THE WHITE HOUSE FAITH OFFICE"),
                row("Jake J. Denton", "POLICY ADVISOR"),
                row("Brittany L. Baldwin", "SENIOR POLICY ADVISOR"),
                row("Tracy L. Johnson", "SENIOR ADVISOR"),
                row("Russ Vought", "DIRECTOR OF THE OFFICE OF MANAGEMENT AND BUDGET"),
            ]
        )
        names = {item["name_en"] for item in classified["members"]}
        self.assertEqual(names, {"Marco A. Rubio", "Paula M. White"})
        self.assertEqual(
            [item["name_en"] for item in classified["unscoped_senior_advisors"]],
            ["Tracy L. Johnson"],
        )

    def test_economic_policy_atp_only(self):
        classified = classify_topical_advisors(
            [
                row(
                    "Kevin A. Hassett",
                    "ASSISTANT TO THE PRESIDENT FOR ECONOMIC POLICY AND DIRECTOR OF THE NATIONAL ECONOMIC COUNCIL",
                ),
                row(
                    "Ryan S. Baasch",
                    "DEPUTY ASSISTANT TO THE PRESIDENT FOR ECONOMIC POLICY AND DEPUTY DIRECTOR OF THE NATIONAL ECONOMIC COUNCIL",
                ),
            ]
        )
        self.assertEqual([item["name_en"] for item in classified["members"]], ["Kevin A. Hassett"])


if __name__ == "__main__":
    unittest.main()
