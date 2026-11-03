(function () {
  var root = document.getElementById("live");
  if (!root) {
    return;
  }
  var url = root.getAttribute("data-refresh-url");
  var kind = root.getAttribute("data-refresh-kind");
  var ms = Number(root.getAttribute("data-refresh-ms"));
  if (!url) {
    return;
  }
  if (!ms || ms < 1000) {
    ms = 15000;
  }
  var statuses = { up: true, down: true, warn: true, pending: true };

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function cell(text) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : String(text);
    return td;
  }

  function statusNode(code, label, error) {
    var td = document.createElement("td");
    var pill = document.createElement("span");
    var safe = statuses[code] ? code : "pending";
    pill.className = "status status-" + safe;
    pill.textContent = label == null ? "" : String(label);
    td.appendChild(pill);
    if (error) {
      var note = document.createElement("span");
      note.className = "status-error";
      note.textContent = String(error);
      td.appendChild(note);
    }
    return td;
  }

  function applyFleet(data) {
    var body = document.getElementById("fleet-body");
    if (!body || !data || !data.servers) {
      return;
    }
    clear(body);
    if (!data.servers.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 6;
      td.className = "empty";
      td.textContent = "No servers yet.";
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }
    data.servers.forEach(function (server) {
      var tr = document.createElement("tr");
      var nameCell = document.createElement("td");
      var id = Number(server.id);
      if (Number.isInteger(id) && id > 0) {
        var link = document.createElement("a");
        link.href = "/servers/" + String(id);
        link.textContent = server.name == null ? "" : String(server.name);
        nameCell.appendChild(link);
      } else {
        nameCell.textContent = server.name == null ? "" : String(server.name);
      }
      tr.appendChild(nameCell);
      tr.appendChild(cell(server.host));
      tr.appendChild(statusNode(server.status, server.status_label, server.error));
      tr.appendChild(cell(server.cpu));
      tr.appendChild(cell(server.memory));
      tr.appendChild(cell(server.checked));
      body.appendChild(tr);
    });
  }

  function setText(id, text) {
    var node = document.getElementById(id);
    if (node) {
      node.textContent = text == null ? "" : String(text);
    }
  }

  function setHidden(id, hidden) {
    var node = document.getElementById(id);
    if (node) {
      node.hidden = hidden;
    }
  }

  function fillTable(bodyId, rows, columns) {
    var body = document.getElementById(bodyId);
    if (!body) {
      return;
    }
    clear(body);
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      columns.forEach(function (key) {
        tr.appendChild(cell(row[key]));
      });
      body.appendChild(tr);
    });
  }

  function applyDetail(data) {
    if (!data || data.servers) {
      return;
    }
    setText("server-name", data.name);
    setText("server-host", data.host);
    setText("status-label", data.status_label);
    var pill = document.getElementById("status-label");
    if (pill) {
      var safe = statuses[data.status] ? data.status : "pending";
      pill.className = "status status-" + safe;
    }
    setText("status-error", data.error || "");
    setHidden("status-error", !data.error);
    setText("checked-at", data.checked);
    setText("cpu-value", data.cpu);
    setText("memory-value", data.memory);
    var hasNetwork = data.network && data.network.length;
    setHidden("network-message", !!hasNetwork);
    setHidden("network-table", !hasNetwork);
    setText("network-message", data.network_message || "");
    if (hasNetwork) {
      fillTable("network-body", data.network, ["iface", "rx", "tx", "rx_rate", "tx_rate"]);
    }
    var hasPorts = data.ports && data.ports.length;
    setHidden("ports-message", !!hasPorts);
    setHidden("ports-table", !hasPorts);
    setText("ports-message", data.ports_message || "");
    if (hasPorts) {
      fillTable("ports-body", data.ports, ["protocol", "address", "port", "process"]);
    }
  }

  function tick() {
    fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    }).then(function (res) {
      var type = res.headers.get("content-type") || "";
      if (!res.ok || type.indexOf("application/json") === -1) {
        return null;
      }
      return res.json();
    }).then(function (data) {
      if (!data) {
        return;
      }
      if (kind === "fleet") {
        applyFleet(data);
      } else {
        applyDetail(data);
      }
    }).catch(function () {});
  }

  var button = document.getElementById("refresh-now");
  if (button) {
    button.addEventListener("click", tick);
  }
  window.setInterval(tick, ms);
})();
