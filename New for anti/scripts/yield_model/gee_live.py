"""Earth Engine login shared by the GEE-based country models
(south_africa, ethiopia, uganda; used when CLIMATE_SOURCE=gee).

Login order:
  1. GEE_SERVICE_ACCOUNT_JSON  -- the service-account key JSON itself (CI secret)
  2. GOOGLE_APPLICATION_CREDENTIALS -- path to that key file (local .env)
  3. the credentials saved by `earthengine authenticate` (original local setup)
EE_PROJECT overrides each model's hard-coded project id, because a service
account can only bill Earth Engine calls to the project it belongs to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def initialize(ee, default_project: str) -> None:
    project = os.environ.get("EE_PROJECT") or default_project
    key_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON", "").strip()
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if key_json:
        email = json.loads(key_json)["client_email"]
        credentials = ee.ServiceAccountCredentials(email, key_data=key_json)
        ee.Initialize(credentials, project=project)
    elif key_path and Path(key_path).exists():
        email = json.loads(Path(key_path).read_text())["client_email"]
        credentials = ee.ServiceAccountCredentials(email, key_file=key_path)
        ee.Initialize(credentials, project=project)
    else:
        ee.Initialize(project=project)

