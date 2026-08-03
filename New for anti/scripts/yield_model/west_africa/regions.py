"""Geographic sampling plan for the first West Africa cocoa data audit.

Weights are deliberately labelled as recent spatial weights. They are not assumed
to describe historical production. Regional labels replace them whenever possible.
"""


POINTS = [
    # Côte d'Ivoire: weights are normalized shares among the main 2023 CCC regions.
    {"country": "Côte d'Ivoire", "region": "Guémon", "lat": 6.83, "lon": -7.35, "weight": 312474},
    {"country": "Côte d'Ivoire", "region": "Cavally", "lat": 6.40, "lon": -7.50, "weight": 277486},
    {"country": "Côte d'Ivoire", "region": "Tonkpi", "lat": 7.40, "lon": -7.60, "weight": 171003},
    {"country": "Côte d'Ivoire", "region": "San-Pédro", "lat": 4.95, "lon": -6.08, "weight": 152348},
    {"country": "Côte d'Ivoire", "region": "Lôh-Djiboua", "lat": 5.84, "lon": -5.36, "weight": 142050},
    {"country": "Côte d'Ivoire", "region": "Gôh", "lat": 6.15, "lon": -5.93, "weight": 138784},
    {"country": "Côte d'Ivoire", "region": "Nawa", "lat": 5.78, "lon": -6.61, "weight": 127718},
    {"country": "Côte d'Ivoire", "region": "Haut-Sassandra", "lat": 6.88, "lon": -6.45, "weight": 105129},
    # Ghana: weights are 2019/20 COCOBOD purchases from the live regional table.
    {"country": "Ghana", "region": "Western North", "lat": 6.30, "lon": -2.90, "weight": 332647},
    {"country": "Ghana", "region": "Ashanti", "lat": 6.75, "lon": -1.60, "weight": 165830},
    {"country": "Ghana", "region": "Eastern", "lat": 6.35, "lon": -0.55, "weight": 89131},
    {"country": "Ghana", "region": "Brong Ahafo", "lat": 7.30, "lon": -2.30, "weight": 88460},
    {"country": "Ghana", "region": "Central", "lat": 5.55, "lon": -1.05, "weight": 85526},
    {"country": "Ghana", "region": "Volta", "lat": 6.55, "lon": 0.45, "weight": 5383},
]


def points_for(country):
    return [point for point in POINTS if point["country"] == country]


def normalized_weight(point):
    peers = points_for(point["country"])
    total = sum(peer["weight"] for peer in peers)
    return point["weight"] / total
