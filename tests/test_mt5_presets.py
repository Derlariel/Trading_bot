from configparser import ConfigParser
from pathlib import Path


def test_small_budget_presets_keep_safety_settings():
    root = Path(__file__).parents[1] / "backtest"
    for deposit in (10, 50, 100):
        config = ConfigParser()
        config.read(root / f"mt5_budget_{deposit}.ini")
        tester = config["Tester"]
        assert tester["Deposit"] == str(deposit)
        assert tester["ExpertParameters"] == "AurumXAU_M15_Baseline.set"
        assert tester["Model"] == "4"
        assert tester["UseRemote"] == tester["UseCloud"] == "0"
