from router import Router
from packet import Packet
import json

class DVrouter(Router):
    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.interfaces = {}
        self.neighbor_dvs = {}
        self.routes = {}
        self.dv = {self.addr: 0}

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            if packet.dst_addr in self.routes:
                cost, next_hop, out_port = self.routes[packet.dst_addr]
                if cost < 16 and out_port is not None:
                    self.send(out_port, packet)
        else:
            sender = packet.src_addr
            rec_dv = json.loads(packet.content)
            if self.neighbor_dvs.get(sender) != rec_dv:
                self.neighbor_dvs[sender] = rec_dv
                if self.update_routes():
                    self.broadcast()

    def handle_new_link(self, port, endpoint, cost):
        self.interfaces[port] = (endpoint, cost)
        self.update_routes()
        self.broadcast()

    def handle_remove_link(self, port):
        if port in self.interfaces:
            endpoint, _ = self.interfaces.pop(port)
            if endpoint in self.neighbor_dvs:
                del self.neighbor_dvs[endpoint]
            self.update_routes()
            self.broadcast()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast()

    def update_routes(self):
        dests = {self.addr}
        for port, (ep, cost) in self.interfaces.items():
            dests.add(ep)
        for nbr, ndv in self.neighbor_dvs.items():
            for d in ndv:
                dests.add(d)
        new_routes = {self.addr: (0, self.addr, None)}
        new_dv = {self.addr: 0}
        for d in dests:
            if d == self.addr:
                continue
            min_cost = 16
            min_nh = None
            min_port = None
            for port, (nbr, link_cost) in self.interfaces.items():
                if nbr == d:
                    if link_cost < min_cost:
                        min_cost = link_cost
                        min_nh = nbr
                        min_port = port
                if nbr in self.neighbor_dvs and d in self.neighbor_dvs[nbr]:
                    c = link_cost + self.neighbor_dvs[nbr][d]
                    if c < min_cost:
                        min_cost = c
                        min_nh = nbr
                        min_port = port
            if min_cost < 16:
                new_routes[d] = (min_cost, min_nh, min_port)
                new_dv[d] = min_cost
            else:
                new_dv[d] = 16
        changed = (new_routes != self.routes)
        self.routes = new_routes
        self.dv = new_dv
        return changed

    def broadcast(self):
        for port, (nbr, link_cost) in self.interfaces.items():
            adv_dv = {}
            for d, c in self.dv.items():
                nh = self.routes.get(d, (None, None, None))[1]
                if nh == nbr and d != self.addr:
                    adv_dv[d] = 16
                else:
                    adv_dv[d] = c
            pkt = Packet(Packet.ROUTING, self.addr, nbr, json.dumps(adv_dv))
            self.send(port, pkt)

    def __repr__(self):
        return f"DVrouter(addr={self.addr}, routes={self.routes})"
