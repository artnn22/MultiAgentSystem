import argparse
import tkinter as tk
from tkinter import ttk

from pathlib import Path

from model import Scenario, Simulation

BASE = Path(__file__).parent
SCENARIOS = {
    "regular": ("Обычный поток", BASE / "scenarios" / "regular.json"),
    "control": ("Контрольный", BASE / "scenario.json"),
}

COURIER_COLORS = ("#216ac4", "#a34717", "#187955")


class CourierApp:
    def __init__(self, root):
        self.root = root
        root.title("МАС · Курьерская доставка")
        root.geometry("1200x830")
        root.minsize(870, 690)
        self.timer = None
        self.logged = 0
        self.logged_activity = 0
        self.logged_tick = -1
        self.selected = tk.IntVar(value=1)

        header = ttk.Frame(root, padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Курьерская доставка", font=("TkDefaultFont", 18, "bold")).pack(side="left")
        self.status = ttk.Label(header)
        self.status.pack(side="right")

        body = ttk.Frame(root, padding=(16, 0, 16, 12))
        body.pack(fill="both", expand=True)
        self.field = tk.Canvas(body, width=460, height=460, background="#f7f9fc", highlightthickness=0)
        self.field.pack(side="left", fill="both", expand=True)
        self.field.bind("<Configure>", lambda _: self.draw_field())
        panel = ttk.Frame(body, width=455, padding=(16, 0, 0, 0))
        panel.pack(side="right", fill="both")
        panel.pack_propagate(False)
        controls = ttk.Frame(panel)
        controls.pack(fill="x", pady=(0, 12))
        self.step_button = ttk.Button(controls, text="Шаг", command=self.step)
        self.step_button.pack(side="left")
        self.play_button = ttk.Button(controls, text="Пуск", command=self.toggle)
        self.play_button.pack(side="left", padx=6)
        ttk.Button(controls, text="Сброс", command=self.reset).pack(side="left")
        self.window_status = ttk.Label(panel, wraplength=420)
        self.window_status.pack(anchor="w", pady=(0, 10))
        config = ttk.Frame(panel)
        config.pack(fill="x", pady=(0, 10), before=self.window_status)
        self.scenario_choice = ttk.Combobox(config, values=[name for name, _ in SCENARIOS.values()],
                                           state="readonly", width=15)
        self.scenario_choice.current(0)
        self.scenario_choice.pack(side="left", padx=(0, 6))
        self.scenario_choice.bind("<<ComboboxSelected>>", lambda _: self.reset())
        self.summary = ttk.Label(panel, wraplength=420)
        self.summary.pack(anchor="w", pady=(0, 8))
        self.choices = ttk.Frame(panel)
        self.choices.pack(fill="x")
        self.courier_choice = ttk.Combobox(self.choices, state="readonly", width=20)
        self.courier_choice.pack(side="left", padx=(0, 6))
        self.courier_choice.bind("<<ComboboxSelected>>", lambda _: self.select(self.courier_choice.current()+1))
        self.order_choice = ttk.Combobox(self.choices, state="readonly", width=17)
        self.order_choice.pack(side="left")
        self.order_choice.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        self.order_details = ttk.Label(panel, wraplength=420, justify="left")
        self.order_details.pack(fill="x", pady=(5, 0))
        self.details = ttk.Label(panel, wraplength=420, justify="left")
        self.details.pack(fill="x", pady=(6, 12))
        ttk.Label(panel, text="Журнал событий", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        log_frame = ttk.Frame(panel)
        log_frame.pack(fill="both", expand=True, pady=(5, 0))
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")
        self.log = tk.Text(log_frame, wrap="word", state="disabled", padx=8, pady=6,
                           yscrollcommand=scrollbar.set, font=("TkDefaultFont", 11))
        self.log.pack(fill="both", expand=True)
        scrollbar.configure(command=self.log.yview)
        self.reset()

    def reset(self):
        self.pause()
        name = tuple(SCENARIOS)[self.scenario_choice.current()]
        self.sim = Simulation(Scenario.load(SCENARIOS[name][1]))
        self.logged = 0
        self.logged_activity = 0
        self.logged_tick = -1
        self.selected.set(1)
        self.courier_choice.configure(values=[c.name for c in self.sim.couriers.values()])
        self.courier_choice.current(0)
        self.order_choice.configure(values=["Выбрать заказ"])
        self.order_choice.current(0)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.refresh()

    def pause(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.play_button.configure(text="Пуск")
        self.step_button.configure(state="normal")

    def toggle(self):
        if self.timer is not None:
            self.pause()
        elif not self.sim.finished:
            self.play_button.configure(text="Пауза")
            self.step_button.configure(state="disabled")
            self.timer = self.root.after(0, self.advance)

    def advance(self):
        self.timer = None
        self.step()
        if not self.sim.finished:
            self.timer = self.root.after(550, self.advance)

    def step(self):
        self.sim.step()
        if self.sim.finished:
            self.pause()
        self.refresh()

    def select(self, courier_id):
        self.selected.set(courier_id)
        self.courier_choice.current(courier_id - 1)
        self.refresh()

    def refresh(self):
        courier = self.sim.couriers[self.selected.get()]
        total = len(self.sim.scenario.orders)
        tick = f"Такт {self.sim.tick}" if self.sim.tick >= 0 else "Готов к запуску"
        self.status.configure(text=f"{tick}   ·   Доставлено {len(self.sim.dispatcher.delivered)}/{total}")
        windows = []
        for pickup in self.sim.pickups.values():
            booking = pickup.current
            window = (f"№{booking.request.courier_id} до т. {booking.end}"
                      if booking else "свободно")
            queue = ", ".join(str(item.courier_id) for item in pickup.waiting) or "—"
            windows.append(f"{pickup.restaurant.name}: {window} · очередь {queue}")
        self.window_status.configure(text="\n".join(windows))
        payout = sum(c.earnings for c in self.sim.couriers.values())
        self.summary.configure(text=f"Выплаты: {payout}")
        if self.sim.finished:
            self.step_button.configure(state="disabled")
            self.play_button.configure(state="disabled")
        else:
            self.play_button.configure(state="normal")
        order = courier.order
        goal = "Ожидает заказ"
        if order:
            target = order.destination if courier.state == "Везёт заказ" else self.sim.pickups[order.restaurant_id].restaurant.position
            goal = f"Заказ №{order.id}, цель {target}, срок {order.deadline}"
        elif courier.reposition_target:
            goal = f"К ресторану «{courier.reposition_target.name}» · доступен для заказов"
        route_preview = list(courier.path)
        path = " → ".join(map(str, route_preview[:4])) or "—"
        if len(route_preview) > 4:
            path += f" → … → {route_preview[-1]}"
        profile = courier.profile
        economy = (f"{profile.name} · до {profile.capacity} кг · заработок {courier.earnings}\n"
                   if profile.capacity else "")
        offer = courier.last_offer if courier.last_offer != courier.last_decision else ""
        self.details.configure(text=(
            f"{economy}{courier.state} · {courier.position}\n{goal}\n"
            f"Маршрут: {path}\n{courier.last_decision}" + (f"\n{offer}" if offer else "")
        ))
        arrived = [o for o in self.sim.scenario.orders if o.arrival <= self.sim.tick]
        index = max(self.order_choice.current(), 0)
        self.order_choice.configure(values=["Выбрать заказ", *(f"Заказ №{o.id}" for o in arrived)])
        self.order_choice.current(index)
        if index:
            inspected = arrived[index-1]
            restaurant = self.sim.pickups[inspected.restaurant_id].restaurant
            winner = self.sim.dispatcher.winners.get(inspected.id)
            payment = self.sim.dispatcher.agreed_payments.get(inspected.id)
            price = f" · {inspected.weight} кг · бюджет {inspected.budget}" if inspected.budget is not None else ""
            executor = f"Курьер №{winner}" if winner else "Ожидает назначения"
            if payment is not None:
                executor += f" · согласовано {payment}"
            self.order_details.configure(text=f"{restaurant.name}{price} · срок {inspected.deadline}\n{executor}")
        else:
            self.order_details.configure(text="")
        self.log.configure(state="normal")
        if self.sim.tick > self.logged_tick:
            self.log.insert("end", f"ТАКТ {self.sim.tick}\n")
            groups = {}
            events = (self.sim.messages[self.logged:]
                      + self.sim.activity[self.logged_activity:])
            for event in events:
                groups.setdefault(event.order_id, []).append(event)
            for order_id, order_events in groups.items():
                title = f"Заказ №{order_id}" if order_id is not None else "Свободные курьеры"
                self.log.insert("end", f"  {title}\n")
                for event in order_events:
                    direction = f" → {event.receiver}" if event.receiver else ""
                    self.log.insert("end", f"  {event.sender}{direction}. {event.reason}\n")
            if not groups:
                self.log.insert("end", "  Ожидание новых событий.\n")
            self.log.insert("end", "\n")
            self.log.see("end")
        self.logged = len(self.sim.messages)
        self.logged_activity = len(self.sim.activity)
        self.logged_tick = self.sim.tick
        self.log.configure(state="disabled")
        self.draw_field()

    def draw_field(self):
        if not hasattr(self, "sim"):
            return
        canvas = self.field
        canvas.delete("all")
        size = self.sim.scenario.size
        cell = min(canvas.winfo_width() - 36, canvas.winfo_height() - 36) / size
        if cell < 4:
            return
        left = (canvas.winfo_width() - size * cell) / 2
        top = (canvas.winfo_height() - size * cell) / 2

        def center(point):
            return left + (point[0] + .5) * cell, top + (point[1] + .5) * cell

        for index in range(size + 1):
            x, y = left + index * cell, top + index * cell
            canvas.create_line(x, top, x, top + size * cell, fill="#cbd5e1")
            canvas.create_line(left, y, left + size * cell, y, fill="#cbd5e1")
        if self.sim.scenario.streets is not None:
            streets = self.sim.scenario.streets
            for y in range(size):
                for x in range(size):
                    if (x, y) in streets:
                        continue
                    cx, cy = center((x, y))
                    half = cell / 2
                    canvas.create_rectangle(cx-half, cy-half, cx+half, cy+half,
                                            fill="#dce3ed", outline="#dce3ed", tags=("building",))
            entrances = {o.destination for o in self.sim.scenario.orders}
            for entrance in entrances:
                x, y = center(entrance)
                canvas.create_rectangle(x-2,y-2,x+2,y+2,fill="#8793a2",outline="")
        for pickup in self.sim.pickups.values():
            restaurant = pickup.restaurant
            x, y = center(restaurant.position)
            radius = cell * .35
            canvas.create_rectangle(x-radius, y-radius, x+radius, y+radius,
                                    outline="#563185", width=2, fill="#e9ddfa")
            canvas.create_text(x, y-cell*.58, text=restaurant.name, fill="#472369",
                               anchor="s", font=("TkDefaultFont", 10, "bold"))
        destinations = {}
        for order in self.sim.scenario.orders:
            if self.sim.scenario.size > 10 and (order.arrival > self.sim.tick
                                              or order.id in self.sim.dispatcher.delivered):
                continue
            destinations.setdefault(order.destination, []).append(order.id)
        for point, ids in destinations.items():
            x, y = center(point)
            canvas.create_oval(x-3,y-3,x+3,y+3,fill="#5523a1",outline="")
            canvas.create_text(x+4,y-3,text="З"+"/".join(map(str,ids)),anchor="sw",
                               fill="#5523a1",font=("TkDefaultFont",9))
        selected = self.sim.couriers[self.selected.get()]
        if selected.path:
            points = [center(point) for point in (selected.position, *selected.path)]
            canvas.create_line(*[coordinate for point in points for coordinate in point],
                               fill="#8295b3", dash=(4, 4), width=2)
        groups = {}
        for courier in self.sim.couriers.values():
            groups.setdefault(courier.position, []).append(courier)
        for point, couriers in groups.items():
            for index, courier in enumerate(couriers):
                x, y = center(point)
                x += (index - (len(couriers) - 1) / 2) * max(cell * .28, 15)
                y += cell * .12
                radius = max(7, cell * (.13 if len(couriers) > 1 else .22))
                color = COURIER_COLORS[{2: 0, 5: 1, 10: 2}.get(courier.profile.capacity, (courier.id - 1) % 3)]
                tag = f"courier{courier.id}"
                outline = "#152135" if courier.id == self.selected.get() else color
                canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                   fill=color, outline=outline, width=2, tags=(tag,))
                canvas.create_text(x, y, text=str(courier.id), fill="white", tags=(tag,))
                canvas.tag_bind(tag, "<Button-1>", lambda _, cid=courier.id: self.select(cid))


def format_message(message):
    if message.receiver == "":
        return f"Такт {message.tick} · {message.sender}. {message.reason}"
    return (
        f"Такт {message.tick} · заказ №{message.order_id} · {message.kind}\n"
        f"{message.sender} → {message.receiver}. {message.reason}"
    )


def main():
    parser = argparse.ArgumentParser(description="Симулятор курьерской МАС")
    parser.add_argument("--trace", action="store_true", help="вывести трассу в терминал")
    parser.add_argument("--scenario", choices=SCENARIOS, default="regular")
    args = parser.parse_args()
    if args.trace:
        sim = Simulation(Scenario.load(SCENARIOS[args.scenario][1]))
        while not sim.finished:
            sim.step()
        for message in sorted(sim.messages + sim.activity, key=lambda event: event.tick):
            print(format_message(message))
        print(sim.dispatcher.delivered)
        return
    root = tk.Tk()
    app = CourierApp(root)
    app.scenario_choice.current(tuple(SCENARIOS).index(args.scenario))
    app.reset()
    root.mainloop()


if __name__ == "__main__":
    main()
