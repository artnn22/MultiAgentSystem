"""Deterministic courier simulation, independent of Tkinter."""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

Point = tuple[int, int]
DISPATCHER = "Диспетчер"
PICKUP = "Пункт выдачи"
LAST_TICK = 100


def distance(first: Point, second: Point) -> int:
    return abs(first[0] - second[0]) + abs(first[1] - second[1])


def route(start: Point, goal: Point) -> deque[Point]:
    x, y = start
    steps = deque()
    while x != goal[0]:
        x += 1 if x < goal[0] else -1
        steps.append((x, y))
    while y != goal[1]:
        y += 1 if y < goal[1] else -1
        steps.append((x, y))
    return steps


@dataclass(frozen=True)
class Order:
    id: int
    arrival: int
    destination: Point
    deadline: int
    restaurant_id: str = "pickup"
    weight: int = 0
    budget: int | None = None


@dataclass(frozen=True)
class Restaurant:
    id: str
    name: str
    position: Point
    loading_ticks: int


@dataclass(frozen=True)
class CourierProfile:
    position: Point
    name: str = "Курьер"
    capacity: int = 0
    tariff: int = 0


@dataclass(frozen=True)
class Scenario:
    size: int
    restaurants: tuple[Restaurant, ...]
    couriers: tuple[CourierProfile, ...]
    orders: tuple[Order, ...]
    horizon: int
    streets: frozenset[Point] | None = None

    def path(self, start, goal):
        if self.streets is None:
            return route(start, goal)
        return deque(self.shortest_path(start, goal))

    def shortest_path(self, start, goal):
        frontier = deque([start])
        parents = {start: None}
        while frontier:
            x, y = current = frontier.popleft()
            if current == goal:
                steps = []
                while parents[current] is not None:
                    steps.append(current)
                    current = parents[current]
                return tuple(reversed(steps))
            for neighbor in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
                if neighbor in self.streets and neighbor not in parents:
                    parents[neighbor] = current
                    frontier.append(neighbor)
        raise ValueError(f"Нет пути между {start} и {goal}")

    @classmethod
    def load(cls, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "restaurants" in data:
            restaurants = tuple(Restaurant(**(row | {"position": tuple(row["position"])}))
                                for row in data["restaurants"])
            couriers = tuple(CourierProfile(**(row | {"position": tuple(row["position"])}))
                             for row in data["couriers"])
        else:
            restaurants = (Restaurant("pickup", PICKUP, tuple(data["pickup"]), data["loading_ticks"]),)
            couriers = tuple(CourierProfile(tuple(point)) for point in data["couriers"])
        orders = tuple(Order(**(row | {"destination": tuple(row["destination"])}))
                       for row in data["orders"])
        size = data["size"]
        streets = None
        if "map" in data:
            rows = json.loads((path.parent / data["map"]).read_text(encoding="utf-8"))
            if len(rows) != size or any(len(row) != size or set(row) - {".", "#"} for row in rows):
                raise ValueError("Карта должна содержать квадрат из улиц (.) и зданий (#).")
            streets = frozenset((x, y) for y, row in enumerate(rows)
                                for x, tile in enumerate(row) if tile == ".")
        scenario = cls(size, restaurants, couriers, orders, data.get("horizon", LAST_TICK), streets)
        if streets is not None:
            points = [r.position for r in restaurants] + [c.position for c in couriers]
            points.extend(o.destination for o in orders)
            if any(point not in streets for point in points):
                raise ValueError("Рестораны, старты и адреса должны находиться на улицах.")
            for point in points:
                scenario.shortest_path(points[0], point)
        return scenario


@dataclass(frozen=True)
class Message:
    tick: int
    sender: str
    receiver: str
    kind: str
    order_id: int | None
    reason: str


@dataclass(frozen=True)
class Estimate:
    courier_id: int
    distance: int
    finish: int
    price: int | None = None


@dataclass
class Courier:
    id: int
    position: Point
    state: str = "Свободен"
    order: Order | None = None
    path: deque[Point] = field(default_factory=deque)
    delivered_count: int = 0
    traveled: int = 0
    reposition_distance: int = 0
    reposition_target: Restaurant | None = None
    needs_reposition: bool = False
    profile: CourierProfile | None = None
    earnings: int = 0
    last_offer: str = ""
    last_decision: str = "Ожидает запрос диспетчера."

    @property
    def name(self) -> str:
        return f"Курьер №{self.id}"

    def estimate(self, order, tick, restaurant, path, position=None):
        if self.order is not None:
            return None, f"Занят заказом №{self.order.id}."
        to_pickup = len(path(self.position if position is None else position, restaurant.position))
        full_path = to_pickup + len(path(restaurant.position, order.destination))
        finish = tick + full_path + restaurant.loading_ticks
        price = None
        calculation = ""
        if order.budget is not None:
            profile = self.profile
            if order.weight > profile.capacity:
                return None, f"Вес {order.weight} кг превышает лимит {profile.capacity} кг."
            price = profile.tariff * full_path + 2 * order.weight + 3 * self.delivered_count + 5
            calculation = (f"Цена {price} = {profile.tariff} × {full_path} + "
                           f"2 × {order.weight} + 3 × {self.delivered_count} + 5. ")
            if price > order.budget:
                return None, f"{calculation}Бюджет {order.budget}."
        if finish > order.deadline:
            return None, f"{calculation}Без очереди прибуду на такте {finish}, срок {order.deadline}."
        return Estimate(self.id, to_pickup, finish, price), (
            f"{calculation}До выдачи {to_pickup} кл. Доставка без очереди на такте "
            f"{finish}, срок {order.deadline}."
        )

    def assign(self, order, pickup, path):
        assert self.order is None
        self.order = order
        self.state = "Едет за заказом"
        self.path = path(self.position, pickup)
        self.reposition_target = None
        self.needs_reposition = False

    def move(self):
        if self.path:
            self.position = self.path.popleft()
            self.traveled += 1
            if self.reposition_target:
                self.reposition_distance += 1


def nearest_ready(estimates):
    return min(estimates, key=lambda item: (item.distance, item.courier_id), default=None)


@dataclass
class Dispatcher:
    pending: list[Order] = field(default_factory=list)
    assigned: dict[int, int] = field(default_factory=dict)
    delivered: dict[int, int] = field(default_factory=dict)
    winners: dict[int, int] = field(default_factory=dict)
    agreed_payments: dict[int, int] = field(default_factory=dict)

    def finish(self, order_id, courier_id, tick):
        if self.assigned.get(order_id) == courier_id:
            self.delivered[order_id] = tick
            del self.assigned[order_id]


@dataclass(frozen=True)
class LoadingRequest:
    tick: int
    courier_id: int
    order_id: int


@dataclass(frozen=True)
class Booking:
    restaurant_id: str
    request: LoadingRequest
    start: int
    end: int


def fifo(requests):
    return min(requests, key=lambda item: (item.tick, item.courier_id), default=None)


@dataclass
class Pickup:
    restaurant: Restaurant
    waiting: list[LoadingRequest] = field(default_factory=list)
    current: Booking | None = None

    def release(self, tick):
        booking = self.current
        if booking is not None and booking.end <= tick:
            self.current = None
            return booking
        return None

    def grant(self, tick, choose):
        if self.current is None and self.waiting:
            request = choose(self.waiting)
            self.waiting.remove(request)
            self.current = Booking(self.restaurant.id, request, tick, tick + self.restaurant.loading_ticks)
            return self.current
        return None


class Simulation:
    def __init__(self, scenario, choose_courier=nearest_ready, choose_loading=fifo):
        self.activity: list[Message] = []
        self.scenario = scenario
        self.choose_courier = choose_courier
        self.choose_loading = choose_loading
        self.tick = -1
        self.couriers = {
            index: Courier(index, profile.position, profile=profile)
            for index, profile in enumerate(scenario.couriers, start=1)
        }
        self.dispatcher = Dispatcher()
        self.pickups = {restaurant.id: Pickup(restaurant) for restaurant in scenario.restaurants}
        self.messages: list[Message] = []
        self.bookings: list[Booking] = []

    @property
    def complete(self):
        return len(self.dispatcher.delivered) == len(self.scenario.orders)

    @property
    def finished(self):
        return (self.complete and not any(c.reposition_target for c in self.couriers.values())
                or self.tick >= self.scenario.horizon)

    def send(self, sender, receiver, kind, order_id, reason):
        message = Message(self.tick, sender, receiver, kind, order_id, reason)
        self.messages.append(message)
        return message

    def assign_orders(self):
        for order in tuple(self.dispatcher.pending):
            estimates = []
            for courier in self.couriers.values():
                self.send(DISPATCHER, courier.name, "ESTIMATE_REQUEST", order.id, "Оценить заказ.")
                estimate, reason = courier.estimate(
                    order, self.tick, self.pickups[order.restaurant_id].restaurant, self.scenario.path
                )
                kind = "READY" if estimate else "REFUSE"
                self.send(courier.name, DISPATCHER, kind, order.id, reason)
                courier.last_decision = f"Заказ №{order.id}. {reason}"
                courier.last_offer = courier.last_decision
                if estimate:
                    estimates.append(estimate)
            winner = self.choose_courier(estimates)
            if winner is None:
                continue
            reason = f"Ближайший готовый курьер. До выдачи {winner.distance} кл."
            self.assign(order, winner.courier_id, "ASSIGN", reason)

    def assign(self, order, courier_id, kind, reason):
        courier = self.couriers[courier_id]
        if order.budget is not None:
            agreed = order.budget
            self.dispatcher.agreed_payments[order.id] = agreed
            reason += f" Выплата при доставке: {agreed}."
        self.send(DISPATCHER, courier.name, kind, order.id, reason)
        courier.assign(order, self.pickups[order.restaurant_id].restaurant.position, self.scenario.path)
        self.dispatcher.winners[order.id] = courier_id
        courier.last_decision = f"Принял заказ №{order.id}. {reason}"
        self.dispatcher.assigned[order.id] = courier.id
        self.dispatcher.pending.remove(order)

    def start_repositioning(self):
        if self.scenario.streets is None:
            return
        for courier in self.couriers.values():
            if not courier.needs_reposition:
                continue
            courier.needs_reposition = False
            options = [(self.scenario.path(courier.position, r.position), r)
                       for r in self.scenario.restaurants]
            path, restaurant = min(options, key=lambda option: (len(option[0]), option[1].id))
            if path:
                courier.path = path
                courier.reposition_target = restaurant
                courier.state = "Едет к ресторану"
                courier.last_decision = f"Ближайшая выдача: {restaurant.name}, {len(path)} кл."
                self.record_activity(courier, "REPOSITION", courier.last_decision)

    def record_activity(self, courier, kind, reason):
        order_id = courier.order.id if courier.order else None
        self.activity.append(Message(self.tick, courier.name, "", kind, order_id, reason))

    def step(self):
        if self.finished:
            return
        self.tick += 1
        # Apply movement chosen at the preceding boundary before new decisions.
        for courier in self.couriers.values():
            previous = courier.position
            courier.move()
            if courier.position != previous:
                self.record_activity(courier, "MOVE", f"{previous} → {courier.position}")
            if courier.reposition_target and not courier.path:
                courier.state = "Свободен"
                courier.last_decision = f"Прибыл к ресторану «{courier.reposition_target.name}»."
                courier.reposition_target = None
                self.record_activity(courier, "REPOSITION_DONE", courier.last_decision)
        for pickup in self.pickups.values():
            released = pickup.release(self.tick)
            if released:
                courier = self.couriers[released.request.courier_id]
                reason = "Загрузка завершена. Выезжаю к получателю."
                self.send(pickup.restaurant.name, courier.name, "LOAD_DONE", courier.order.id, reason)
                courier.state = "Везёт заказ"
                courier.path = self.scenario.path(courier.position, courier.order.destination)
                courier.last_decision = reason
        for courier in self.couriers.values():
            if courier.state == "Везёт заказ" and not courier.path:
                order = courier.order
                late = max(0, self.tick - order.deadline)
                reason = f"Доставлен на такте {self.tick}. Просрочка: {late}."
                self.send(courier.name, DISPATCHER, "DELIVERED", order.id, reason)
                self.dispatcher.finish(order.id, courier.id, self.tick)
                courier.delivered_count += 1
                courier.earnings += self.dispatcher.agreed_payments.get(order.id, 0)
                courier.order = None
                courier.needs_reposition = True
                courier.state = "Свободен"
                courier.last_decision = f"Заказ №{order.id}. {reason}"
                courier.last_offer = courier.last_decision
        arrivals = sorted(
            (order for order in self.scenario.orders if order.arrival == self.tick),
            key=lambda order: order.id,
        )
        for order in arrivals:
            self.dispatcher.pending.append(order)
            self.send("Среда", DISPATCHER, "ARRIVAL", order.id, f"Срок {order.deadline}.")
        self.assign_orders()
        self.start_repositioning()
        for courier in self.couriers.values():
            if courier.state == "Едет за заказом" and not courier.path:
                reason = f"Прибыл к пункту выдачи на такте {self.tick}. Запросил загрузку."
                pickup = self.pickups[courier.order.restaurant_id]
                self.send(courier.name, pickup.restaurant.name, "LOAD_REQUEST", courier.order.id, reason)
                pickup.waiting.append(LoadingRequest(self.tick, courier.id, courier.order.id))
                courier.state = "Ждёт загрузку"
                courier.last_decision = reason
        for pickup in self.pickups.values():
            booking = pickup.grant(self.tick, self.choose_loading)
            if booking:
                courier = self.couriers[booking.request.courier_id]
                reason = f"Окно предоставлено на такты [{booking.start}, {booking.end})."
                self.send(pickup.restaurant.name, courier.name, "LOAD_GRANTED", booking.request.order_id, reason)
                self.bookings.append(booking)
                courier.state = "Загружается"
                courier.last_decision = reason
