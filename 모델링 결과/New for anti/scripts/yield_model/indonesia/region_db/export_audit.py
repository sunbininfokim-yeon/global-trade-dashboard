"""Export transparent CSV summaries from the BPS panel database."""

import os
import sqlite3
import sys

import pandas as pd

from .build_db import DATA, DATABASE


def main():
    connection = sqlite3.connect(DATABASE)
    observations = pd.read_sql_query(
        "SELECT * FROM observations ORDER BY crop, year, province, category",
        connection)
    issues = pd.read_sql_query(
        "SELECT * FROM audit_issues ORDER BY severity, publication_id, year, province",
        connection)
    coverage = pd.read_sql_query("""
        SELECT crop, product, year, data_status,
               COUNT(DISTINCT province) AS provinces,
               SUM(CASE WHEN category='total' AND production_tonnes IS NOT NULL
                        THEN 1 ELSE 0 END) AS provinces_with_production,
               SUM(CASE WHEN category='total' THEN production_tonnes ELSE 0 END)
                   AS province_production_sum
        FROM observations
        GROUP BY crop, product, year, data_status
        ORDER BY crop, year
    """, connection)
    connection.close()
    observations.to_csv(os.path.join(DATA, "province_observations.csv"), index=False)
    issues.to_csv(os.path.join(DATA, "audit_issues.csv"), index=False)
    coverage.to_csv(os.path.join(DATA, "coverage.csv"), index=False)
    print("[bps:export] observations {} coverage {} issues {}".format(
        len(observations), len(coverage), len(issues)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
