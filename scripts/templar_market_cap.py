#!/usr/bin/env python3
"""Fetch Templar (subnet 3) market cap in USD."""

import json
import subprocess

TAOSTATS_API_KEY = "tao-1ff82bd0-d289-4aec-a5bd-42dda3eb9517:a6795a25"
TEMPLAR_NETUID = 3


def curl_json(url: str, headers: dict | None = None) -> dict:
    cmd = ["curl", "-s", url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def main():
    taostats = curl_json(
        f"https://api.taostats.io/api/dtao/pool/latest/v1?netuid={TEMPLAR_NETUID}",
        {"Authorization": TAOSTATS_API_KEY},
    )
    coingecko = curl_json(
        "https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd",
    )

    market_cap_tao = float(taostats["data"][0]["market_cap"]) / 1e9
    tao_usd = coingecko["bittensor"]["usd"]
    market_cap_usd = market_cap_tao * tao_usd

    print(f"Templar market cap: ${market_cap_usd:,.0f}")


if __name__ == "__main__":
    main()
