(() => {
  const vscode = acquireVsCodeApi();
  const state = {
    graph: null,
    selectedNodeId: null,
    layout: new Map(),
    edgeSet: new Set(),
    transform: { x: 24, y: 24, scale: 1 },
    dragging: false,
    dragStart: { x: 0, y: 0 },
    transformStart: { x: 0, y: 0 },
  };

  const el = {
    fileName: document.getElementById('fileName'),
    statusText: document.getElementById('statusText'),
    viewport: document.getElementById('viewport'),
    canvas: document.getElementById('canvas'),
    edges: document.getElementById('edges'),
    nodes: document.getElementById('nodes'),
    emptyState: document.getElementById('emptyState'),
    details: document.getElementById('details'),
    zoomOut: document.getElementById('zoomOut'),
    zoomIn: document.getElementById('zoomIn'),
    fit: document.getElementById('fit'),
    reparse: document.getElementById('reparse'),
  };

  window.addEventListener('message', (event) => {
    const message = event.data;
    if (!message || message.action !== 'state') {
      return;
    }
    renderState(message.state);
  });

  el.reparse.addEventListener('click', () => vscode.postMessage({ action: 'requestReparse' }));
  el.zoomIn.addEventListener('click', () => zoomAtCenter(1.16));
  el.zoomOut.addEventListener('click', () => zoomAtCenter(0.86));
  el.fit.addEventListener('click', fitGraph);

  el.viewport.addEventListener('wheel', (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.1 : 0.9;
    zoomAt(event.clientX, event.clientY, factor);
  }, { passive: false });

  el.viewport.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || event.target.closest('.node')) {
      return;
    }
    state.dragging = true;
    state.dragStart = { x: event.clientX, y: event.clientY };
    state.transformStart = { x: state.transform.x, y: state.transform.y };
    el.viewport.classList.add('dragging');
    el.viewport.setPointerCapture(event.pointerId);
  });

  el.viewport.addEventListener('pointermove', (event) => {
    if (!state.dragging) {
      return;
    }
    state.transform.x = state.transformStart.x + event.clientX - state.dragStart.x;
    state.transform.y = state.transformStart.y + event.clientY - state.dragStart.y;
    applyTransform();
  });

  el.viewport.addEventListener('pointerup', (event) => {
    state.dragging = false;
    el.viewport.classList.remove('dragging');
    try {
      el.viewport.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture may already be released when the webview loses focus.
    }
  });

  vscode.postMessage({ action: 'loadState' });

  function renderState(viewerState) {
    el.fileName.textContent = viewerState.fileName || 'TorchScript graph';
    el.statusText.textContent = statusLabel(viewerState);
    state.selectedNodeId = viewerState.selectedNodeId || null;

    if (viewerState.status === 'loading') {
      clearGraph();
      el.emptyState.classList.remove('hidden');
      el.emptyState.textContent = progressMessage(viewerState);
      renderDetails(null, viewerState);
      return;
    }

    if (viewerState.status === 'error') {
      clearGraph();
      el.emptyState.classList.remove('hidden');
      el.emptyState.textContent = viewerState.error ? viewerState.error.message : 'Unable to parse graph.';
      renderError(viewerState);
      return;
    }

    state.graph = normalizeGraph(viewerState.graph);
    el.emptyState.classList.remove('hidden');
    el.emptyState.textContent = 'Rendering graph...';
    renderGraph(state.graph);
    renderDetails(null, viewerState);
    requestAnimationFrame(fitGraph);
  }

  function normalizeGraph(graph) {
    const nodes = Array.isArray(graph && graph.nodes) ? graph.nodes : [];
    const edges = Array.isArray(graph && graph.edges) ? graph.edges : [];
    return { ...graph, nodes, edges };
  }

  function clearGraph() {
    state.graph = null;
    state.layout = new Map();
    state.edgeSet = new Set();
    el.nodes.replaceChildren();
    el.edges.replaceChildren();
  }

  function renderGraph(graph) {
    clearGraph();
    const layout = computeLayout(graph.nodes, graph.edges);
    state.layout = layout.positions;
    state.edgeSet = new Set(graph.edges.map((edge) => `${edge.source}->${edge.target}`));
    el.canvas.style.width = `${layout.width}px`;
    el.canvas.style.height = `${layout.height}px`;
    el.edges.setAttribute('width', String(layout.width));
    el.edges.setAttribute('height', String(layout.height));
    el.edges.setAttribute('viewBox', `0 0 ${layout.width} ${layout.height}`);

    for (const edge of graph.edges) {
      const source = layout.positions.get(edge.source);
      const target = layout.positions.get(edge.target);
      if (!source || !target) {
        continue;
      }
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.classList.add('edge');
      path.dataset.source = edge.source;
      path.dataset.target = edge.target;
      path.dataset.edgeId = edge.id || `${edge.source}->${edge.target}`;
      const sx = source.x + layout.nodeWidth / 2;
      const sy = source.y + layout.nodeHeight;
      const tx = target.x + layout.nodeWidth / 2;
      const ty = target.y;
      const mid = Math.max(34, (ty - sy) / 2);
      path.setAttribute('d', `M ${sx} ${sy} C ${sx} ${sy + mid}, ${tx} ${ty - mid}, ${tx} ${ty}`);
      el.edges.appendChild(path);
    }

    for (const node of graph.nodes) {
      const pos = layout.positions.get(node.id);
      if (!pos) {
        continue;
      }
      const div = document.createElement('div');
      div.className = 'node';
      div.dataset.nodeId = node.id;
      div.style.left = `${pos.x}px`;
      div.style.top = `${pos.y}px`;
      div.style.height = `${layout.nodeHeight}px`;
      const kind = document.createElement('div');
      kind.className = 'node-kind';
      kind.textContent = node.kind || node.label || node.id;
      const meta = document.createElement('div');
      meta.className = 'node-meta';
      meta.textContent = compactNodeMeta(node);
      div.append(kind, meta);
      div.addEventListener('click', () => selectNode(node.id));
      el.nodes.appendChild(div);
    }

    el.emptyState.classList.toggle('hidden', graph.nodes.length > 0);
    if (!graph.nodes.length) {
      el.emptyState.textContent = 'No graph nodes were returned.';
    }
    applySelection();
  }

  function computeLayout(nodes, edges) {
    const nodeWidth = 184;
    const nodeHeight = 64;
    const xGap = 64;
    const yGap = 92;
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const incoming = new Map(nodes.map((node) => [node.id, 0]));
    const outgoing = new Map(nodes.map((node) => [node.id, []]));

    for (const edge of edges) {
      if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) {
        continue;
      }
      incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
      outgoing.get(edge.source).push(edge.target);
    }

    const queue = nodes.filter((node) => (incoming.get(node.id) || 0) === 0).map((node) => node.id);
    const ranks = new Map(nodes.map((node) => [node.id, 0]));
    const remainingIncoming = new Map(incoming);
    const visited = new Set();

    while (queue.length) {
      const id = queue.shift();
      visited.add(id);
      for (const target of outgoing.get(id) || []) {
        ranks.set(target, Math.max(ranks.get(target) || 0, (ranks.get(id) || 0) + 1));
        remainingIncoming.set(target, (remainingIncoming.get(target) || 0) - 1);
        if ((remainingIncoming.get(target) || 0) === 0) {
          queue.push(target);
        }
      }
    }

    for (const node of nodes) {
      if (!visited.has(node.id)) {
        ranks.set(node.id, (ranks.get(node.id) || 0) + 1);
      }
    }

    const layers = new Map();
    for (const node of nodes) {
      const rank = ranks.get(node.id) || 0;
      if (!layers.has(rank)) {
        layers.set(rank, []);
      }
      layers.get(rank).push(node.id);
    }

    const sortedRanks = [...layers.keys()].sort((a, b) => a - b);
    const maxLayer = Math.max(1, ...[...layers.values()].map((layer) => layer.length));
    const width = Math.max(520, maxLayer * nodeWidth + (maxLayer - 1) * xGap + 80);
    const height = Math.max(360, sortedRanks.length * nodeHeight + Math.max(0, sortedRanks.length - 1) * yGap + 80);
    const positions = new Map();

    sortedRanks.forEach((rank, rankIndex) => {
      const layer = layers.get(rank);
      const layerWidth = layer.length * nodeWidth + Math.max(0, layer.length - 1) * xGap;
      const startX = Math.max(40, (width - layerWidth) / 2);
      layer.forEach((id, index) => {
        positions.set(id, {
          x: startX + index * (nodeWidth + xGap),
          y: 40 + rankIndex * (nodeHeight + yGap),
        });
      });
    });

    return { positions, width, height, nodeWidth, nodeHeight };
  }

  function compactNodeMeta(node) {
    const parts = [];
    if (node.scope) {
      parts.push(node.scope);
    }
    const inputs = Array.isArray(node.inputs) ? node.inputs.length : 0;
    const outputs = Array.isArray(node.outputs) ? node.outputs.length : 0;
    parts.push(`${inputs} in / ${outputs} out`);
    return parts.join(' | ');
  }

  function selectNode(nodeId) {
    state.selectedNodeId = state.selectedNodeId === nodeId ? null : nodeId;
    vscode.postMessage({ action: 'selectNode', nodeId: state.selectedNodeId });
    const selected = state.graph ? state.graph.nodes.find((node) => node.id === state.selectedNodeId) : null;
    applySelection();
    renderDetails(selected, { graph: state.graph, status: 'ready' });
  }

  function applySelection() {
    const selected = state.selectedNodeId;
    const neighbors = new Set();
    if (selected && state.graph) {
      for (const edge of state.graph.edges) {
        if (edge.source === selected) {
          neighbors.add(edge.target);
        }
        if (edge.target === selected) {
          neighbors.add(edge.source);
        }
      }
    }

    for (const nodeEl of el.nodes.querySelectorAll('.node')) {
      const id = nodeEl.dataset.nodeId;
      nodeEl.classList.toggle('selected', id === selected);
      nodeEl.classList.toggle('neighbor', neighbors.has(id));
      nodeEl.classList.toggle('dimmed', Boolean(selected) && id !== selected && !neighbors.has(id));
    }

    for (const edgeEl of el.edges.querySelectorAll('.edge')) {
      const active = Boolean(selected) && (edgeEl.dataset.source === selected || edgeEl.dataset.target === selected);
      edgeEl.classList.toggle('active', active);
    }
  }

  function renderDetails(node, viewerState) {
    el.details.replaceChildren();
    if (!state.graph && viewerState && viewerState.status !== 'ready') {
      appendHeading(el.details, 'Graph');
      renderProgress(el.details, viewerState);
      return;
    }

    if (!node) {
      appendHeading(el.details, 'Graph');
      const graph = (viewerState && viewerState.graph) || state.graph;
      if (graph && graph.model) {
        appendKeyValues(el.details, [
          ['File', graph.model.fileName || ''],
          ['Torch', graph.model.torchVersion || 'unknown'],
          ['Nodes', String((graph.nodes || []).length)],
          ['Edges', String((graph.edges || []).length)],
        ]);
      } else {
        appendText(el.details, 'Select a node to inspect details.');
      }
      if (viewerState && viewerState.diagnostics) {
        appendSubheading(el.details, 'Diagnostics');
        appendKeyValues(el.details, diagnosticRows(viewerState.diagnostics));
      }
      if (graph && Array.isArray(graph.warnings) && graph.warnings.length) {
        appendSubheading(el.details, 'Warnings');
        for (const warning of graph.warnings) {
          const div = document.createElement('div');
          div.className = 'warning';
          div.textContent = warning;
          el.details.appendChild(div);
        }
      }
      return;
    }

    appendHeading(el.details, node.kind || node.label || node.id);
    appendKeyValues(el.details, [
      ['ID', node.id],
      ['Label', node.label || ''],
      ['Scope', node.scope || ''],
    ]);

    appendSubheading(el.details, 'Inputs');
    appendValues(el.details, node.inputs);
    appendSubheading(el.details, 'Outputs');
    appendValues(el.details, node.outputs);
    appendSubheading(el.details, 'Attributes');
    appendPre(el.details, JSON.stringify(node.attributes || {}, null, 2));
  }

  function renderError(viewerState) {
    el.details.replaceChildren();
    const error = viewerState.error || {};
    const box = document.createElement('div');
    box.className = 'error';
    appendHeading(box, error.code || 'Error');
    appendText(box, error.message || 'Unable to parse this file.');
    appendSubheading(box, 'Action');
    appendText(box, error.action || 'Check the parser configuration and try again.');
    if (error.details !== undefined) {
      appendSubheading(box, 'Details');
      appendPre(box, JSON.stringify(error.details, null, 2));
    }
    el.details.appendChild(box);
  }

  function renderProgress(parent, viewerState) {
    const progress = viewerState.progress || {};
    appendText(parent, progress.message || 'Loading graph...');
    appendKeyValues(parent, [
      ['Stage', progress.stage || viewerState.status || 'loading'],
      ['Elapsed', typeof progress.elapsedMs === 'number' ? `${(progress.elapsedMs / 1000).toFixed(1)} s` : ''],
    ]);
    if (viewerState.diagnostics) {
      appendSubheading(parent, 'Diagnostics');
      appendKeyValues(parent, diagnosticRows(viewerState.diagnostics));
    }
    appendSubheading(parent, 'Limits');
    appendKeyValues(parent, [
      ['Max file', String(viewerState.limits && viewerState.limits.maxFileBytes || '')],
      ['Max nodes', String(viewerState.limits && viewerState.limits.maxNodes || '')],
      ['Max edges', String(viewerState.limits && viewerState.limits.maxEdges || '')],
      ['Timeout', viewerState.limits ? `${viewerState.limits.timeoutMs} ms` : ''],
    ]);
  }

  function diagnosticRows(diagnostics) {
    return Object.entries(diagnostics).map(([key, value]) => [key, String(value)]);
  }

  function progressMessage(viewerState) {
    return viewerState && viewerState.progress && viewerState.progress.message
      ? viewerState.progress.message
      : 'Loading graph...';
  }

  function statusLabel(viewerState) {
    if (viewerState.status === 'loading' && viewerState.progress && viewerState.progress.stage) {
      return `loading: ${viewerState.progress.stage}`;
    }
    if (viewerState.status === 'ready' && viewerState.progress && viewerState.progress.message) {
      return viewerState.progress.message;
    }
    return viewerState.status;
  }

  function appendHeading(parent, text) {
    const heading = document.createElement('h2');
    heading.textContent = text;
    parent.appendChild(heading);
  }

  function appendSubheading(parent, text) {
    const heading = document.createElement('h3');
    heading.textContent = text;
    parent.appendChild(heading);
  }

  function appendText(parent, text) {
    const div = document.createElement('div');
    div.className = 'value';
    div.textContent = text;
    parent.appendChild(div);
  }

  function appendKeyValues(parent, rows) {
    const grid = document.createElement('div');
    grid.className = 'kv';
    for (const [key, value] of rows) {
      const keyEl = document.createElement('div');
      keyEl.className = 'key';
      keyEl.textContent = key;
      const valueEl = document.createElement('div');
      valueEl.className = 'value';
      valueEl.textContent = value;
      grid.append(keyEl, valueEl);
    }
    parent.appendChild(grid);
  }

  function appendValues(parent, values) {
    if (!Array.isArray(values) || values.length === 0) {
      appendText(parent, 'None');
      return;
    }
    for (const value of values) {
      const pill = document.createElement('span');
      pill.className = 'pill';
      pill.textContent = `${value.name || '<unnamed>'}: ${value.type || '<unknown>'}`;
      parent.appendChild(pill);
    }
  }

  function appendPre(parent, text) {
    const pre = document.createElement('pre');
    pre.textContent = text;
    parent.appendChild(pre);
  }

  function zoomAtCenter(factor) {
    const rect = el.viewport.getBoundingClientRect();
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
  }

  function zoomAt(clientX, clientY, factor) {
    const rect = el.viewport.getBoundingClientRect();
    const before = {
      x: (clientX - rect.left - state.transform.x) / state.transform.scale,
      y: (clientY - rect.top - state.transform.y) / state.transform.scale,
    };
    state.transform.scale = clamp(state.transform.scale * factor, 0.18, 2.8);
    state.transform.x = clientX - rect.left - before.x * state.transform.scale;
    state.transform.y = clientY - rect.top - before.y * state.transform.scale;
    applyTransform();
  }

  function fitGraph() {
    if (!state.graph || !state.graph.nodes.length) {
      return;
    }
    const rect = el.viewport.getBoundingClientRect();
    const width = Number.parseFloat(el.canvas.style.width) || 600;
    const height = Number.parseFloat(el.canvas.style.height) || 400;
    const scale = clamp(Math.min((rect.width - 40) / width, (rect.height - 40) / height), 0.18, 1.2);
    state.transform.scale = scale;
    state.transform.x = Math.max(20, (rect.width - width * scale) / 2);
    state.transform.y = Math.max(20, (rect.height - height * scale) / 2);
    applyTransform();
  }

  function applyTransform() {
    el.canvas.style.transform = `translate(${state.transform.x}px, ${state.transform.y}px) scale(${state.transform.scale})`;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }
})();
