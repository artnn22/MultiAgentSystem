"""Reproducible headless comparisons on the same model as the GUI."""

import argparse
import csv
from pathlib import Path
from statistics import mean

from model import MODES, Scenario, Simulation

BASE = Path(__file__).parent
SCENARIOS = {
    "regular": ("Обычный поток", BASE / "scenarios" / "regular.json"),
    "heavy": ("Тяжёлые заказы", BASE / "scenarios" / "heavy.json"),
    "peak": ("Пиковый спрос", BASE / "scenarios" / "peak.json"),
    "control": ("Контрольный", BASE / "scenario.json"),
    "intervals": ("Интервалы", BASE / "scenarios" / "intervals.json"),
    "burst": ("Всплеск", BASE / "scenarios" / "burst.json"),
}


def run(sim):
    while not sim.finished:
        sim.step()
    return sim


def metrics(sim):
    arrived = [order for order in sim.scenario.orders if order.arrival <= sim.tick]
    done = sim.dispatcher.delivered
    latencies = [done[order.id] - order.arrival for order in arrived if order.id in done]
    restaurant_waits = {restaurant_id: [] for restaurant_id in sim.pickups}
    for booking in sim.bookings:
        restaurant_waits[booking.restaurant_id].append(booking.start - booking.request.tick)
    waits = [wait for times in restaurant_waits.values() for wait in times]
    on_time = sum(order.id in done and done[order.id] <= order.deadline for order in arrived)
    traveled = sum(c.traveled for c in sim.couriers.values())
    reposition = sum(c.reposition_distance for c in sim.couriers.values())
    return {
        "arrived": len(arrived),
        "delivered": len(done),
        "on_time": on_time,
        "on_time_fraction": round(on_time / len(arrived), 4) if arrived else None,
        "unfinished": len(arrived) - len(done),
        "distance": traveled,
        "order_distance": traveled - reposition,
        "reposition_distance": reposition,
        "mean_latency": round(mean(latencies), 2) if latencies else None,
        "mean_load_wait": round(mean(waits), 2) if waits else None,
        "messages": sum(message.kind != "ARRIVAL" for message in sim.messages),
        "end_tick": sim.tick,
        "payout": sum(courier.earnings for courier in sim.couriers.values()),
        "wait_by_restaurant": "/".join(
            f"{rid}:{mean(times):.2f}" if times else f"{rid}:—"
            for rid, times in restaurant_waits.items()
        ),
        "earnings_by_courier": "/".join(str(c.earnings) for c in sim.couriers.values()),
        "deliveries_by_courier": "/".join(str(c.delivered_count) for c in sim.couriers.values()),
    }


def compare(scenario_keys=("regular", "heavy", "peak")):
    for key in scenario_keys:
        _, path = SCENARIOS[key]
        scenario = Scenario.load(path)
        for mode in MODES:
            sim = run(Simulation(scenario, mode=mode))
            yield {"scenario": key, "mode": mode, **metrics(sim)}


def main():
    parser = argparse.ArgumentParser(description="Сравнение двух механизмов")
    parser.add_argument("--csv", type=Path, default=BASE / "results.csv")
    args = parser.parse_args()
    rows = list(compare())
    with args.csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(args.csv)


if __name__ == "__main__":
    main()
