#!/usr/bin/env python3
"""Fetch Templar (subnet 3) market cap from the Taostats API."""

import json
import subprocess

TAOSTATS_API_KEY = "tao-1ff82bd0-d289-4aec-a5bd-42dda3eb9517:a6795a25"
TEMPLAR_NETUID = 3
ENDPOINT = f"https://api.taostats.io/api/dtao/pool/latest/v1?netuid={TEMPLAR_NETUID}"


def fetch_templar_market_cap() -> dict:
    result = subprocess.run(
        ["curl", "-s", ENDPOINT, "-H", f"Authorization: {TAOSTATS_API_KEY}"],
        capture_output=True,
        text=True,
        check=True,
    )
    body = json.loads(result.stdout)

    if not body.get("data"):
        raise RuntimeError("No data returned from Taostats API")

    return body["data"][0]


def format_rao_as_tao(rao_str: str) -> str:
    """Convert rao value (string) to TAO (divide by 1e9)."""
    return f"{float(rao_str) / 1e9:,.2f}"


def main():
    data = fetch_templar_market_cap()

    market_cap_tao = format_rao_as_tao(data["market_cap"])
    liquidity_tao = format_rao_as_tao(data["liquidity"])
    price = float(data["price"])

    print(f"=== Templar (subnet {data['netuid']}) — ${data['symbol'].upper()} ===")
    print(f"Market Cap:        {market_cap_tao} TAO")
    print(f"Liquidity:         {liquidity_tao} TAO")
    print(f"Price:             {price:.6f} TAO per GAMMA")
    print(f"Rank:              {data['rank']}")
    print(f"Fear & Greed:      {data['fear_and_greed_index']} ({data['fear_and_greed_sentiment']})")
    print()
    print("Price changes:")
    print(f"  1 hour:  {float(data['price_change_1_hour']):+.2f}%")
    print(f"  1 day:   {float(data['price_change_1_day']):+.2f}%")
    print(f"  1 week:  {float(data['price_change_1_week']):+.2f}%")
    print(f"  1 month: {float(data['price_change_1_month']):+.2f}%")
    print()
    print(f"Market cap change (24h): {float(data['market_cap_change_1_day']):+.2f}%")
    print(f"24h volume: {format_rao_as_tao(str(data['tao_volume_24_hr']))} TAO")
    print(f"24h buys/sells: {data['buys_24_hr']} / {data['sells_24_hr']}")


if __name__ == "__main__":
    main()
