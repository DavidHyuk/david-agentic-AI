# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check the compatibility and capacity exposed by the Spark Strata launcher."""

import runpy
from pathlib import Path


def test_strata_serves_the_new_model_and_the_current_provider_alias(tmp_path):
    launcher = runpy.run_path(str(Path(__file__).parents[1] / "local-model/run_flash_next_nvfp4.py"))
    pack = tmp_path / "weights"
    projector = tmp_path / "mmproj.gguf"

    config = launcher["strata_config"](tmp_path / "runtime", pack, projector)
    args = config["args"]

    assert config["model_name"] == "Qwen3.8-Flash-Next-FP4-Local"
    assert config["aliases"] == ["Qwen3.8-Flash-Next-UD-IQ4_XS"]
    assert config["parallel"] == 2
    assert args[args.index("--max-context") + 1] == "131072"
    assert args[args.index("--ple-gguf") + 1] == str(pack / "ple-nvfp4.gguf")
    assert args[args.index("--mtp") + 1] == str(pack / "mtp/rt")
    assert config["vision"]["mmproj"] == str(projector)
