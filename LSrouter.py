from router import Router
from packet import Packet
import json
import heapq

class LSrouter(Router):
    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.interfaces = {}
        self.seq = 0
        self.link_states = {}
        self.forwarding_table = {}

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            if packet.dst_addr in self.forwarding_table:
                out_port = self.forwarding_table[packet.dst_addr]
                if out_port is not None:
                    self.send(out_port, packet)
        else:
            data = json.loads(packet.content)
            adv = data["adv"]
            seq = data["seq"]
            links = data["links"]
            if adv not in self.link_states or seq > self.link_states[adv][0]:
                self.link_states[adv] = (seq, links)
                self.recompute_routes()
                for p, (ep, cost) in self.interfaces.items():
                    if p != port:
                        pkt = Packet(Packet.ROUTING, self.addr, ep, packet.content)
                        self.send(p, pkt)

    def handle_new_link(self, port, endpoint, cost):
        self.interfaces[port] = (endpoint, cost)
        self.broadcast_lsp()
        for adv, (seq, links) in self.link_states.items():
            if adv != self.addr:
                pkt = Packet(Packet.ROUTING, self.addr, endpoint, json.dumps({"adv": adv, "seq": seq, "links": links}))
                self.send(port, pkt)

    def handle_remove_link(self, port):
        if port in self.interfaces:
            del self.interfaces[port]
            self.broadcast_lsp()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.broadcast_lsp()

    def broadcast_lsp(self):
        self.seq += 1
        local_links = {ep: cost for ep, cost in self.interfaces.values()}
        self.link_states[self.addr] = (self.seq, local_links)
        self.recompute_routes()
        msg = json.dumps({"adv": self.addr, "seq": self.seq, "links": local_links})
        for port, (ep, cost) in self.interfaces.items():
            pkt = Packet(Packet.ROUTING, self.addr, ep, msg)
            self.send(port, pkt)

    def recompute_routes(self):
        graph = {}
        for adv, (seq, links) in self.link_states.items():
            graph[adv] = links
        pq = [(0, self.addr)]
        dist = {self.addr: 0}
        first_port = {}
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            for v, cost in graph.get(u, {}).items():
                new_d = d + cost
                if new_d < dist.get(v, float("inf")):
                    dist[v] = new_d
                    if u == self.addr:
                        p = None
                        for port, (ep, c) in self.interfaces.items():
                            if ep == v:
                                p = port
                                break
                        first_port[v] = p
                    else:
                        first_port[v] = first_port[u]
                    heapq.heappush(pq, (new_d, v))
        self.forwarding_table = {dst: p for dst, p in first_port.items() if p is not None}

    def __repr__(self):
        return f"LSrouter(addr={self.addr}, table={self.forwarding_table})"
