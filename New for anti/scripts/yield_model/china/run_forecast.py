"""Publish China's observation-only crop-monitor panel.

This module keeps its historical name because the weekly GitHub Action calls
``python -m china.run_forecast``.  The tested field and import models all fail
their honest baselines, so this entrypoint must not put their trend
extrapolations back on the website.  It delegates to the reference publisher
instead.

The failed model artifacts, training tables and ``predict.py`` remain in the
package for audit and reproduction.  They are evidence for *why* no forecast
is published, not a source of dashboard forecast points.
"""

from .build_reference import main


if __name__ == "__main__":
    main()
