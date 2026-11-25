// Thin wrappers around the Chatchup API (/api/v1/pcap, see PROJECT.md 2.6).

export function createApi(base) {
  async function request(path, options = {}) {
    const response = await fetch(base + path, options);
    let body = null;
    try {
      body = await response.json();
    } catch {
      // empty or not JSON (204)
    }
    if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
    return body;
  }
  const window = ({ tStart = null, tEnd = null } = {}) => {
    const p = new URLSearchParams();
    if (tStart !== null) p.set("t_start", tStart);
    if (tEnd !== null) p.set("t_end", tEnd);
    return p;
  };
  const json = (body) => ({ method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

  return {
    list: () => request("/captures"),
    capture: (id) => request(`/captures/${id}`),
    upload(file) {
      const form = new FormData();
      form.append("file", file);
      return request("/captures", { method: "POST", body: form });
    },
    remove: (id) => request(`/captures/${id}`, { method: "DELETE" }),
    graph(id, { protocol = "", minPackets = 1, ...w } = {}) {
      const p = window(w);
      p.set("protocol", protocol);
      p.set("min_packets", minPackets);
      return request(`/captures/${id}/graph?${p}`);
    },
    overview: (id, w) => request(`/captures/${id}/overview?${window(w)}`),
    timeline: (id) => request(`/captures/${id}/timeline`),
    host: (id, ip) => request(`/captures/${id}/hosts/${encodeURIComponent(ip)}`),
    summary: (id) => request(`/captures/${id}/summary`, { method: "POST" }),
    ask: (id, question) => request(`/captures/${id}/chat`, json({ question })),
  };
}
