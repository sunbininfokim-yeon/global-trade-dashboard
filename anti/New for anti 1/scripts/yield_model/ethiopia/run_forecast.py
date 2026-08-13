from .collect import build
from .challenger import run as run_challenger
from .predict import predict
from .train import train


def run(refresh: bool = False):
    build(refresh=refresh); train(); run_challenger(); return predict()


if __name__ == "__main__": run()
