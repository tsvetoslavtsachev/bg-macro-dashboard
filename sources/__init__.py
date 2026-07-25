from sources.ecb_adapter import EcbAdapter
from sources.eurostat_adapter import EurostatAdapter

def build_adapters() -> dict:
    """Връща инстанцирани адаптери по име на източник."""
    return {
        "eurostat": EurostatAdapter(),
        "ecb": EcbAdapter(),
    }
