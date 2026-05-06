# TorchScript DAG Viewer

Readonly VS Code custom editor MVP for trusted TorchScript traced `.pt` files. The extension runs a local Python parser, converts a TorchScript graph to versioned JSON, and renders a top-down operator DAG in a webview.

## Install for local development

1. Open this folder in VS Code: `extensions/torchscript-dag-viewer`.
2. Run `npm install` when network access is available.
3. Run `npm run compile`.
4. Press `F5` to launch an Extension Development Host.
5. In the development host, open a trusted workspace and open a `.pt` file.

This repository also includes checked JavaScript output under `out/` so the MVP can run without rebuilding when dependencies are unavailable.

## Configure Python

Set `torchscriptDagViewer.pythonPath` to the Python interpreter that has PyTorch installed. If unset, the extension tries `python3` and then `python`.

Example VS Code setting:

```json
{
  "torchscriptDagViewer.pythonPath": "/path/to/venv/bin/python"
}
```

The parser imports `torch` and calls `torch.jit.load(model_path, map_location="cpu")`.

## Open a `.pt` file

Open a trusted TorchScript traced `.pt` file in VS Code. The custom editor activates for `*.pt`, starts in a loading state, and then shows:

- a top-down DAG with nodes and directed edges,
- mouse-wheel zoom and drag panning,
- node selection,
- highlighted incoming/outgoing neighbors,
- a right-side details panel with node kind, scope, inputs, outputs, and attributes.

Use the `Reparse` button in the webview after changing settings or replacing the file.

## Limits and actionable errors

The extension reports actionable errors for:

- restricted workspaces,
- missing Python,
- missing PyTorch,
- parser timeout,
- parser crash or invalid output,
- files larger than `torchscriptDagViewer.maxFileBytes`,
- graphs larger than `torchscriptDagViewer.maxNodes` or `torchscriptDagViewer.maxEdges`.

Default limits are 100 MiB, 2000 nodes, 4000 edges, and 30 seconds.

## Security model and limitations

This is a trusted-file viewer, not a sandbox. PyTorch documents that `torch.jit.load` can execute arbitrary code through malicious pickle data. Only open `.pt` files from trusted sources and only in trusted VS Code workspaces.

The extension declares `capabilities.untrustedWorkspaces.supported: false` and checks `vscode.workspace.isTrusted` before parsing. The webview uses `localResourceRoots`, `asWebviewUri`, a Content Security Policy, and a JSON message protocol with a small action whitelist.

Out of scope for this MVP:

- VS Code Web support,
- consistent remote SSH, Dev Container, or Codespaces behavior,
- hardened parser isolation through containers or a restricted runtime.
