// Canvas module — the M4 React Flow surface.
//
//   <Canvas projectId={id} />   — drop into the canvas route's <main>
//
//   <Toolbox ... />              — left rail (also exported in case a
//                                  future layout reuses it)
//
//   CanvasNode / CanvasEdge     — the per-element renderers, used by
//                                  the React Flow instance internally
//                                  via the `nodeTypes` / `edgeTypes`
//                                  maps. Exported only for tests.

export { Canvas, default } from './Canvas';
export { Toolbox, DRAG_MIME } from './Toolbox';
export { CanvasNode, type CanvasNodeData } from './CanvasNode';
export { CanvasEdge, type CanvasEdgeData } from './CanvasWire';
